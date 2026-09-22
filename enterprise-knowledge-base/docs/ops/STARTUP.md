# 启动手册

## 环境要求

| 组件 | 最低版本 | 说明 |
|------|---------|------|
| Docker | 24+ | 需要 Compose v2 支持 |
| Docker Compose | 2.20+ | `docker compose`（非 `docker-compose`） |
| RAM | ≥16GB | Milvus(4G) + ES(2G) + MySQL + 后端 |
| 磁盘 | ≥50GB 可用 | 向量索引 + ES 索引 + 日志保留 |
| 操作系统 | Linux / Windows(WSL2) / macOS | — |

## 启动流程（推荐，本地开发）

### 一键启动（开发模式）

```powershell
.\start.ps1
```

脚本自动执行以下检查，任一失败会明确提示：

| 检查项 | 作用 | 失败时提示 |
|--------|------|-----------|
| 端口占用预检 | 防止本地 npm 与 Docker 抢 80/443/5173/5175/8000/8080 | 停止本地服务后重试 |
| 失效系统代理残留 | 防止容器外网（LLM/热榜）因残留代理失败 | 自动清除并提示重启 Docker |
| 必需镜像预检 | 缺镜像时提示将触发 pull | 检查 daemon.json 镜像源 |
| 容器健康等待 | 等 MySQL/ES/Milvus 等 healthy | 超时输出失败容器日志 |
| API/前端/后台就绪 | 等三端 HTTP 200 | 超时输出对应容器日志 |
| CORS/文章/外网/CSP/照片 | 业务层自检 | 定位具体配置问题 |

启动成功后访问：
- Vue 前端：`https://localhost`
- React 管理后台：`https://localhost/app/`
- 后端 API：`https://localhost/api`

> 请始终使用 `https://localhost` 入口，勿直接用 5173/5175 原始端口，避免缓存/跨域问题。

### 手动启动（等价命令）

```bash
# 开发模式
docker compose up -d

# 生产模式（见下方"生产部署"）
docker compose -f docker-compose.prod.yml up -d
```

## 首次部署

### 1. 克隆代码

```bash
git clone <repo-url> /opt/knowledge-base
cd /opt/knowledge-base
```

### 2. 配置环境变量

```bash
cp .env.prod .env
```

编辑 `.env`，必须修改以下密钥：

| 变量 | 生成方式 |
|------|---------|
| `MYSQL_ROOT_PASSWORD` | `openssl rand -hex 16` |
| `MYSQL_PASSWORD` | `openssl rand -hex 16` |
| `POSTGRES_PASSWORD` | `openssl rand -hex 16` |
| `MINIO_ACCESS_KEY` | `openssl rand -hex 8` |
| `MINIO_SECRET_KEY` | `openssl rand -hex 16` |
| `JWT_SECRET_KEY` | `openssl rand -hex 32` |
| `LLM_API_KEY` | 必填：DeepSeek API Key |
| `CORS_ORIGINS` | 生产域名，逗号分隔 |

### 3. 生成 SSL 证书

**自签名（内网/演示）：**

```bash
cd docker/ssl
openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
  -keyout server.key -out server.crt \
  -subj "/CN=your-server-ip"
```

**Let's Encrypt（公网域名）：**

```bash
certbot certonly --standalone -d your-domain.com
cp /etc/letsencrypt/live/your-domain.com/fullchain.pem docker/ssl/server.crt
cp /etc/letsencrypt/live/your-domain.com/privkey.pem docker/ssl/server.key
```

### 4. 启动所有服务

```bash
docker compose -f docker-compose.prod.yml up -d
```

### 5. 等待健康检查通过

```bash
docker compose -f docker-compose.prod.yml ps
```

所有容器状态应为 `healthy` 或 `Up`。首次启动 Milvus/ES 约需 2-3 分钟。

### 6. 验证部署

```bash
# API 健康检查
curl -k https://localhost/api/health

# 前端访问
curl -k https://localhost/

# Grafana（如果启用）
curl http://localhost:3000/api/health
```

## 默认账号

| 系统 | 地址 | 账号 | 密码 |
|------|------|------|------|
| 管理后台 | `https://<host>/` | `admin` | `Admin@123` |
| Grafana | `http://localhost:3000` | 见 `.env` GRAFANA_USER | 见 `.env` GRAFANA_PASSWORD |
| MinIO Console | `http://localhost:9001` | 见 `.env` MINIO_ACCESS_KEY | 见 `.env` MINIO_SECRET_KEY |
| API 文档 | `https://<host>/api/docs` | — | — |

## 端口映射

| 端口 | 服务 | 协议 |
|------|------|------|
| 80 | Nginx HTTP | 重定向到 443 |
| 443 | Nginx HTTPS | 入口网关 |
| 8000 | FastAPI 后端 | 仅内网（expose） |
| 3306 | MySQL | 可关闭外部映射 |
| 5432 | PostgreSQL | 可关闭外部映射 |
| 6379 | Redis | 可关闭外部映射 |
| 9200 | Elasticsearch | 可关闭外部映射 |
| 19530 | Milvus | 可关闭外部映射 |
| 9001 | MinIO Console | 可关闭外部映射 |
| 3000 | Grafana | 可关闭外部映射 |
| 9090 | Prometheus | 可关闭外部映射 |

## 停止与重启

```bash
# 停止
docker compose -f docker-compose.prod.yml down

# 重启（保留数据卷）
docker compose -f docker-compose.prod.yml restart

# 重建并重启（代码更新后）
docker compose -f docker-compose.prod.yml up -d --build

# 仅重建后端
docker compose -f docker-compose.prod.yml up -d --build backend
```

## 防火墙建议

```bash
# 仅开放必要端口
ufw allow 80/tcp
ufw allow 443/tcp
# 内网监控端口（仅内网访问）
ufw allow from 10.0.0.0/8 to any port 3000
ufw allow from 10.0.0.0/8 to any port 9090
```

## 常见问题排查

### 1. Docker 拉取镜像失败

**现象**：`docker compose up` 时卡在 pull，或报 `connect: connection refused` / `actively refused`。

**原因**：本地镜像缺失触发拉取，但镜像源不可达，或 Docker 走系统代理到失效端口。

**排查**：
```bash
# 本地已有镜像则不会拉取
docker images

# 检查镜像源是否可达
curl -sk -o /dev/null -w "%{http_code}\n" --max-time 8 https://hub.rat.dev/v2/
curl -sk -o /dev/null -w "%{http_code}\n" --max-time 8 https://docker.m.daocloud.io/v2/

# 查看配置的镜像源
type %USERPROFILE%\.docker\daemon.json
```

**处理**：
- 若 `daemon.json` 含失效镜像源（如 `docker.1panel.live` 返回 000），移除后重启 Docker Desktop
- 若系统代理残留指向失效端口，按下方"容器外网全挂"处理

### 2. 前端功能不能用（AI 写作 / 热榜 / 照片）

**现象**：页面能打开，但 AI 分析失败、热榜为空、照片无法显示。

**原因**：均与**容器外网**或 **CSP 头**有关，而非前后端断连。

**排查**：
```bash
# ① 容器外网（LLM/热榜依赖）
docker exec kb-backend python -c "import urllib.request; print(urllib.request.urlopen('https://api.deepseek.com', timeout=8).status)"
# 预期 401/200；若 Connection refused / timed out 则外网故障

# ② CSP 是否含 blob:（照片依赖）
curl -sk -I https://localhost/app/ | findstr "img-src"

# ③ 热榜
curl -sk "https://localhost/api/admin/articles/hot-topics?refresh=true"
```

**处理**：
- 外网故障 → 检查宿主机系统代理残留（`reg query "HKCU\Software\Microsoft\Windows\CurrentVersion\Internet Settings" /v ProxyEnable`，若为 1 且代理端口无监听则置 0），然后重启 Docker Desktop
- CSP 缺 `blob:` → 检查 `docker/nginx/conf.d/default.conf` 的 `img-src` 是否含 `blob:`，修改后 `docker exec kb-nginx nginx -s reload`

### 3. 前后端"没连上"

**现象**：页面能打开但接口请求失败，或控制台报错。

**排查**：前后端代码均使用相对路径 `/api`，经 nginx 网关转发，**不存在独立直连**：
```bash
# 网关链路自检
curl -sk https://localhost/api/health          # 预期 200
curl -sk -o NUL -w "%{http_code}\n" https://localhost/app/   # 预期 200
```
若接口 200 但页面异常，多为**浏览器缓存旧版 JS**，用无痕窗口或 Ctrl+F5 硬刷新验证。

### 4. 重新启动后一切正常

**现象**：重启 Docker 或项目后功能恢复。

**原因**：Docker 配置（镜像源/代理）已刷新，或本地镜像已存在无需再拉取。`start.ps1` 已内置上述检查，直接使用一键脚本可避免大部分此类问题。
