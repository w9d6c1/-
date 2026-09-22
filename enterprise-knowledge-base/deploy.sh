#!/bin/bash
set -e

DOMAIN="<生产域名>"
EMAIL="<管理员邮箱>"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# 非 root 时自动用 sudo 重新执行（apt/ufw/systemctl 需要 root）
if [ "$(id -u)" -ne 0 ]; then
  echo "    检测到非 root 用户，使用 sudo 重新执行..."
  exec sudo -E bash "$SCRIPT_DIR/deploy.sh"
fi
# 记录原始用户（git 操作后恢复属主用）
ORIG_USER="${SUDO_USER:-root}"

echo "===================================="
echo "  企业知识库系统 — 生产部署"
echo "  域名: $DOMAIN"
echo "===================================="
echo ""

# ============================================
# ① 安装系统依赖
# ============================================
echo ">>> ① 安装系统依赖..."
apt update -qq
apt install -y -qq certbot ufw openssl > /dev/null 2>&1
echo "    ✔ certbot + ufw + openssl 已安装"

# ============================================
# ② 配置防火墙
# ============================================
echo ""
echo ">>> ② 配置防火墙..."
ufw default deny incoming
ufw allow 22/tcp
ufw allow 80/tcp
ufw allow 443/tcp
ufw --force enable
echo "    ✔ 防火墙已启用 (22/80/443 开放)"

# ============================================
# ②-bis 配置 Docker 国内镜像源
# ============================================
echo ""
echo ">>> ②-bis 配置 Docker 国内镜像源..."
if [ ! -f /etc/docker/daemon.json ]; then
  mkdir -p /etc/docker
  cat > /etc/docker/daemon.json <<'EOF'
{
  "registry-mirrors": [
    "https://mirror.ccs.tencentyun.com",
    "https://docker.m.daocloud.io",
    "https://dockerproxy.com"
  ]
}
EOF
  systemctl restart docker
  echo "    ✔ 已写入 daemon.json 并重启 Docker"
else
  echo "    ✔ daemon.json 已存在，跳过"
fi

# ============================================
# ③ 创建 Swap
# ============================================
echo ""
echo ">>> ③ 创建 Swap (2G)..."
if [ ! -f /swapfile ]; then
  fallocate -l 2G /swapfile
  chmod 600 /swapfile
  mkswap /swapfile
  swapon /swapfile
  echo '/swapfile none swap sw 0 0' >> /etc/fstab
  echo "    ✔ Swap 2G 已创建"
else
  echo "    ✔ Swap 已存在"
fi

# ============================================
# ④ 拉取代码
# ============================================
echo ""
echo ">>> ④ 拉取最新代码..."
GIT_ROOT="$(git -C "$SCRIPT_DIR" rev-parse --show-toplevel 2>/dev/null || true)"
if [ -z "$GIT_ROOT" ]; then
  echo "    ✘ 仓库不存在，请先 git clone"
  echo "    git clone <你的仓库地址> ~/kb && cd ~/kb/enterprise-knowledge-base"
  exit 1
fi
echo "    ✔ git 根目录: $GIT_ROOT"
git -C "$GIT_ROOT" pull origin main || true
[ -n "$ORIG_USER" ] && chown -R "$ORIG_USER":"$ORIG_USER" "$GIT_ROOT" 2>/dev/null || true
echo "    ✔ 代码已更新"

# ============================================
# ⑤ 生产配置
# ============================================
echo ""
echo ">>> ⑤ 复制生产环境变量..."
if [ ! -f .env.prod ]; then
  echo "    ✘ .env.prod 不存在，请先 scp 上传"
  exit 1
fi
cp .env.prod .env
echo "    ✔ .env.prod → .env"

# ============================================
# ⑥ SSL 证书
# ============================================
echo ""
echo ">>> ⑥ 申请 Let's Encrypt SSL 证书..."
echo "    先停 Nginx 释放 80 端口..."
docker compose -f docker-compose.prod.yml -f docker-compose.tencent.yml stop nginx 2>/dev/null || true

CERT_OK=0
if certbot certificates 2>/dev/null | grep -q "$DOMAIN"; then
  echo "    证书已存在，尝试续期..."
  if certbot renew --cert-name "$DOMAIN" --force-renewal; then
    CERT_OK=1
  fi
else
  echo "    首次申请证书..."
  if certbot certonly --standalone \
    -d "$DOMAIN" -d "www.$DOMAIN" \
    --agree-tos -m "$EMAIL" --non-interactive; then
    CERT_OK=1
  else
    echo "    ⚠ Let's Encrypt 申请失败（可能 DNS 未指向本机），使用自签名证书兜底"
  fi
fi

if [ "$CERT_OK" -eq 1 ]; then
  echo "    复制证书到项目..."
  cp /etc/letsencrypt/live/$DOMAIN/fullchain.pem docker/ssl/server.crt
  cp /etc/letsencrypt/live/$DOMAIN/privkey.pem   docker/ssl/server.key
else
  echo "    生成自签名证书兜底..."
  mkdir -p docker/ssl
  openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
    -keyout docker/ssl/server.key \
    -out docker/ssl/server.crt \
    -subj "/CN=$DOMAIN" 2>/dev/null
fi
echo "    ✔ SSL 证书就绪"

# ============================================
# ⑦ 部署前自检
# ============================================
echo ""
echo ">>> ⑦ 运行部署前自检..."
if [ -f scripts/preflight-check.sh ]; then
  bash scripts/preflight-check.sh || true
  echo "    ✔ 前置检查已运行（警告项不中断部署）"
else
  echo "    ✘ scripts/preflight-check.sh 不存在，跳过自检"
fi

# ============================================
# ⑧ 构建 + 启动
# ============================================
echo ""
echo ">>> ⑧ 构建镜像 + 启动全部服务..."
# Version tagging + rollback preparation
VERSION=$(git rev-parse --short HEAD 2>/dev/null || date +%Y%m%d%H%M%S)
echo "    VERSION=$VERSION"

for svc in kb-backend kb-frontend; do
  current=$(docker images -q "$svc:latest" 2>/dev/null)
  if [ -n "$current" ]; then
    docker tag "$svc:latest" "$svc:previous" 2>/dev/null || true
    echo "    Kept previous version $svc:previous for rollback"
  fi
done

docker compose \
  -f docker-compose.prod.yml \
  -f docker-compose.tencent.yml \
  build --build-arg APP_VERSION="$VERSION"

docker tag kb-backend:latest "kb-backend:$VERSION" 2>/dev/null || true
docker tag kb-frontend:latest "kb-frontend:$VERSION" 2>/dev/null || true

docker compose \
  -f docker-compose.prod.yml \
  -f docker-compose.tencent.yml \
  up -d

# ============================================
# ⑨ 数据库建表与基础种子 (01-schema.sql 已裁剪为仅建库)
# ============================================
echo ""
echo ">>> ⑨ 数据库建表与基础种子 (init_schema)..."
COMPOSE_ARGS="-f docker-compose.prod.yml -f docker-compose.tencent.yml"
SCHEMA_OK=0
for i in 1 2 3 4 5; do
  if docker compose $COMPOSE_ARGS exec -T backend python -m app.scripts.init_schema; then
    echo "    ✔ 数据库 schema/种子已就绪"
    SCHEMA_OK=1
    break
  fi
  echo "    后端未就绪，第 ${i}/5 次重试..."
  sleep 20
done
if [ "$SCHEMA_OK" -ne 1 ]; then
  echo "    ✘ init_schema 未成功，请检查 kb-backend 日志" >&2
  docker logs kb-backend --tail 50 2>&1 || true
  exit 1
fi

echo ""
docker ps --format "table {{.Names}}\t{{.Status}}" | head -20

echo ""
echo "===================================="
echo "  ✔ 部署完成"
echo "===================================="
echo ""
echo "  Web        https://$DOMAIN"
echo "  Admin      用户名: admin  密码: <默认管理员密码>"
echo ""
echo "  验证命令:"
echo "    docker ps | wc -l             # 应为 15 行 (含 header)"
echo "    docker stats --no-stream      # 查看内存"
echo "    df -h /                       # 查看磁盘"
echo ""
echo "  SSL 自动续期 (已安装 certbot timer):"
echo "    certbot renew --dry-run"
echo ""
