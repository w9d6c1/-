# 生产环境部署手册

> 最后更新: 2026-08-13  
> 适用版本: v0.1.0+  
> 部署方式: Docker Compose (生产模式)  
> 目标域名: <生产域名>

---

## 目录

1. [前置条件](#1-前置条件)
2. [服务器初始化](#2-服务器初始化)
3. [部署步骤](#3-部署步骤)
4. [部署后验证](#4-部署后验证)
5. [运维操作](#5-运维操作)
6. [故障排查](#6-故障排查)
7. [回滚流程](#7-回滚流程)
8. [安全加固建议](#8-安全加固建议)

---

## 1. 前置条件

### 1.1 服务器配置要求

| 配置项 | 最低要求 | 推荐配置 | 说明 |
|--------|---------|---------|------|
| CPU | 4 核 | 8 核 | Milvus + ES 需要较多 CPU |
| 内存 | 8 GB | 16 GB | 生产配置压缩至 ~3.5GB，留余量 |
| 磁盘 | 50 GB | 100 GB | ES 索引 + Milvus 向量 + 日志 |
| 系统 | Ubuntu 20.04+ / CentOS 7+ | Ubuntu 22.04 | 需要 systemd 支持 |

### 1.2 网络要求

- **公网 IP**: 服务器需有固定公网 IP
- **域名**: `<生产域名>` 已配置 DNS A 记录指向服务器 IP
- **端口**: 
  - 80 (HTTP, 自动重定向到 HTTPS)
  - 443 (HTTPS, 主入口)
  - 22 (SSH, 管理用)

### 1.3 准备工作

- [ ] 域名 DNS A 记录已配置
- [ ] SSH 访问权限已获取
- [ ] `.env.prod` 配置文件已准备（项目根目录）
- [ ] 本地已安装 `scp` 或 `rsync` 工具

---

## 2. 服务器初始化

### 2.1 安装 Docker + Docker Compose

```bash
# 安装 Docker (官方脚本)
curl -fsSL https://get.docker.com | sh

# 启动 Docker
systemctl start docker
systemctl enable docker

# 验证安装
docker --version  # 应 >= 24.0
docker compose version  # 应 >= 2.20
```

**国内服务器加速（可选）：**
```bash
# 配置 Docker 镜像源（腾讯云/阿里云）
mkdir -p /etc/docker
cat > /etc/docker/daemon.json <<EOF
{
  "registry-mirrors": [
    "https://mirror.ccs.tencentyun.com",
    "https://docker.m.daocloud.io"
  ]
}
EOF

systemctl restart docker
```

### 2.2 创建 Swap (2GB)

```bash
# 检查是否已有 Swap
free -h

# 创建 Swap（如果没有）
fallocate -l 2G /swapfile
chmod 600 /swapfile
mkswap /swapfile
swapon /swapfile

# 持久化
echo '/swapfile none swap sw 0 0' >> /etc/fstab

# 验证
free -h  # 应显示 Swap: 2.0G
```

### 2.3 配置防火墙

```bash
# 安装 ufw（如果没有）
apt update
apt install -y ufw

# 配置规则
ufw default deny incoming
ufw default allow outgoing
ufw allow 22/tcp   # SSH
ufw allow 80/tcp   # HTTP
ufw allow 443/tcp  # HTTPS

# 启用防火墙
ufw enable
ufw status  # 验证
```

**腾讯云安全组（额外配置）：**
- 登录腾讯云控制台 → 云服务器 → 安全组
- 添加入站规则：
  - 80/tcp (HTTP)
  - 443/tcp (HTTPS)
  - 22/tcp (SSH, 建议限制 IP)

---

## 3. 部署步骤

### 3.1 克隆代码

```bash
# SSH 登录服务器
ssh user@your-server-ip

# 克隆代码
cd /opt
git clone <your-repo-url> knowledge-base
cd knowledge-base
```

### 3.2 上传生产配置

**方式一：scp 上传（推荐）**
```bash
# 在本地执行
cd enterprise-knowledge-base
scp .env.prod user@your-server-ip:/opt/knowledge-base/
```

**方式二：手动创建**
```bash
# 在服务器上创建
cd /opt/knowledge-base
vi .env.prod
# 粘贴 .env.prod 内容（从本地复制）
```

### 3.3 应用生产配置

```bash
cd /opt/knowledge-base

# 备份开发配置（如果有）
[ -f .env ] && mv .env .env.dev.bak

# 应用生产配置
cp .env.prod .env

# 验证关键配置
grep "DEBUG=" .env          # 应为 false
grep "CORS_ORIGINS=" .env   # 应为 https://<生产域名>
```

### 3.4 运行前置自检

```bash
# 运行自检脚本（自动修复可修复项）
bash scripts/preflight-check.sh --fix

# 查看检查结果
# 应显示:
# - PASS: Docker 版本
# - PASS: 内存/磁盘/CPU
# - PASS: .env 配置
# - PASS: SSL 证书（自动生成自签名）
# - PASS: 端口可用性
```

**腾讯云适配说明：**
- 如果内存检查 FAIL（要求 14GB，实际 8GB），可忽略
- `docker-compose.tencent.yml` 已优化资源占用至 ~3.5GB

### 3.5 执行一键部署

```bash
# 执行部署脚本
bash deploy.sh

# 脚本自动完成:
# 1. 安装 certbot + ufw + openssl
# 2. 配置防火墙（22/80/443）
# 3. 创建 Swap（如果没有）
# 4. 拉取最新代码（git pull）
# 5. 申请 Let's Encrypt SSL 证书
# 6. 构建 Docker 镜像
# 7. 启动所有服务
# 8. 初始化数据库 schema
```

**部署耗时：**
- 首次部署: 10-15 分钟（拉取镜像 + 构建）
- 后续部署: 3-5 分钟（仅重建应用镜像）

### 3.6 查看部署结果

```bash
# 查看所有容器状态
docker ps

# 应显示 15 个容器（含 header）:
# kb-nginx, kb-waf, kb-backend, kb-frontend
# kb-mysql, kb-postgres, kb-redis, kb-elasticsearch
# kb-milvus, kb-etcd, kb-minio
# kb-prometheus, kb-grafana, kb-loki, kb-promtail

# 查看资源占用
docker stats --no-stream

# 查看磁盘使用
df -h /
```

---

## 4. 部署后验证

### 4.1 服务健康检查

```bash
# 1. 容器状态
docker compose -f docker-compose.prod.yml ps
# 所有容器应为 healthy 或 Up

# 2. API 健康检查
curl -k https://<生产域名>/api/health
# 应返回: {"status":"ok","version":"0.1.0"}

# 3. 前端访问
curl -k -I https://<生产域名>/
# 应返回: HTTP/2 200

# 4. 管理后台
curl -k -I https://<生产域名>/app/
# 应返回: HTTP/2 200

# 5. SSL 证书
echo | openssl s_client -connect <生产域名>:443 -servername <生产域名> 2>/dev/null | openssl x509 -noout -dates
# 应显示 Let's Encrypt 证书有效期
```

### 4.2 功能验证

**浏览器访问测试：**

1. **Vue 前端**: `https://<生产域名>/`
   - 首页加载正常
   - AI 对话功能可用
   - 登录/注册流程正常

2. **React 管理后台**: `https://<生产域名>/app/`
   - 登录页面加载正常
   - 使用默认账号登录: `admin` / `<默认管理员密码>`
   - 知识库管理、文档管理功能可用

3. **API 文档**: `https://<生产域名>/api/docs`
   - Swagger UI 加载正常
   - 可测试 API 接口

**命令行功能测试：**

```bash
# 智能体对话测试
curl -k -X POST https://<生产域名>/api/agent/customer/chat \
  -H "Content-Type: application/json" \
  -d '{"question":"你好","session_id":"test-001"}'
# 应返回 AI 回答

# 管理后台登录测试
curl -k -X POST https://<生产域名>/api/admin/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"<默认管理员密码>"}'
# 应返回 JWT token
```

### 4.3 数据库验证

```bash
# MySQL 连接测试
docker compose -f docker-compose.prod.yml exec mysql \
  mysqladmin ping -u root -p'<REDACTED>'
# 应返回: mysqld is alive

# PostgreSQL 连接测试
docker compose -f docker-compose.prod.yml exec postgres \
  pg_isready -U postgres
# 应返回: accepting connections

# Redis 连接测试
docker compose -f docker-compose.prod.yml exec redis \
  redis-cli PING
# 应返回: PONG

# Elasticsearch 集群状态
curl -s http://localhost:9200/_cluster/health | grep status
# 应返回: "status":"green" 或 "yellow"

# Milvus 健康检查
curl -s http://localhost:9091/healthz
# 应返回: OK
```

### 4.4 监控验证

```bash
# Grafana 访问
curl -s http://localhost:3000/api/health
# 应返回: {"commit":"...","database":"ok","version":"..."}

# 浏览器访问: http://<server-ip>:3000
# 登录: admin / <REDACTED>
# 应能看到 4 个预设看板:
# - 服务概览
# - 业务洞察
# - 知识质量
# - 安全态势

# Prometheus 指标采集
curl -s http://localhost:9090/api/v1/targets | grep health
# 应显示所有 target 为 "up"
```

---

## 5. 运维操作

### 5.1 日志查看

```bash
# 查看后端日志
docker logs kb-backend --tail 100 -f

# 查看 Nginx 访问日志
docker logs kb-nginx --tail 100 -f

# 查看 WAF 审计日志
docker compose -f docker-compose.prod.yml exec waf \
  cat /var/log/modsec_audit.log | tail -50

# 查看所有容器日志（实时）
docker compose -f docker-compose.prod.yml logs -f
```

### 5.2 服务重启

```bash
# 重启单个服务
docker compose -f docker-compose.prod.yml restart backend

# 重启所有服务（保留数据）
docker compose -f docker-compose.prod.yml restart

# 停止所有服务
docker compose -f docker-compose.prod.yml down

# 启动所有服务
docker compose -f docker-compose.prod.yml up -d
```

### 5.3 代码更新

```bash
# 1. 拉取最新代码
cd /opt/knowledge-base
git pull origin main

# 2. 重建并重启（仅后端）
docker compose -f docker-compose.prod.yml up -d --build backend

# 3. 重建并重启（全部服务）
docker compose -f docker-compose.prod.yml up -d --build

# 4. 验证更新
docker ps  # 检查容器状态
curl -k https://<生产域名>/api/health  # 检查 API
```

### 5.4 数据库备份

**手动备份：**
```bash
# 执行备份脚本
bash scripts/backup.sh

# 备份文件保存在: ./backups/YYYYMMDD_HHMMSS/
# 包含:
# - mysql_all.sql (MySQL 全量备份)
# - postgres_langgraph.sql (PostgreSQL 备份)
# - minio/ (MinIO 对象存储)
# - ES snapshot (Elasticsearch 快照)
```

**定时备份（cron）：**
```bash
# 编辑 crontab
crontab -e

# 添加每日凌晨 2 点自动备份
0 2 * * * cd /opt/knowledge-base && /bin/bash scripts/backup.sh >> /var/log/kb-backup.log 2>&1

# 验证 cron
crontab -l
```

**备份保留策略：**
```bash
# 保留最近 7 天的备份
find ./backups -type d -mtime +7 -exec rm -rf {} +
```

### 5.5 SSL 证书续期

```bash
# Let's Encrypt 证书有效期 90 天，certbot 自动续期

# 手动测试续期
certbot renew --dry-run

# 查看证书状态
certbot certificates

# 手动强制续期
certbot renew --force-renewal

# 续期后重启 Nginx
docker compose -f docker-compose.prod.yml restart nginx
```

### 5.6 资源监控

```bash
# 实时资源占用
docker stats

# 磁盘使用
df -h /
du -sh /opt/knowledge-base/backups/*

# 内存使用
free -h

# 查看大文件
find /opt/knowledge-base -type f -size +100M
```

---

## 6. 故障排查

### 6.1 容器启动失败

**现象：** `docker ps` 显示容器状态为 `Restarting` 或 `Exited`

**排查步骤：**
```bash
# 1. 查看失败容器日志
docker logs kb-backend --tail 100

# 2. 检查依赖服务
docker compose -f docker-compose.prod.yml ps
# 确认 MySQL/Redis/ES/Milvus 均为 healthy

# 3. 检查端口冲突
ss -tlnp | grep -E '80|443|8000|3306|5432|6379|9200|19530'

# 4. 检查磁盘空间
df -h /

# 5. 检查内存
free -h
docker stats --no-stream
```

**常见原因与解决：**

| 原因 | 解决方案 |
|------|---------|
| 内存不足 (OOM) | 增加 Swap 或升级服务器配置 |
| 磁盘空间不足 | 清理日志/备份，扩容磁盘 |
| 端口被占用 | 停止占用端口的进程，或修改配置 |
| 依赖服务未就绪 | 等待健康检查通过，或重启依赖服务 |
| 配置文件错误 | 检查 `.env` 格式，对比 `.env.prod` |

### 6.2 API 无法访问

**现象：** `curl https://<生产域名>/api/health` 返回 502/504

**排查步骤：**
```bash
# 1. 检查 Nginx 状态
docker logs kb-nginx --tail 50

# 2. 检查后端状态
docker logs kb-backend --tail 50

# 3. 检查 WAF 状态
docker logs kb-waf --tail 50

# 4. 测试后端直连
docker exec kb-backend curl -s http://localhost:8000/health

# 5. 检查 SSL 证书
ls -la docker/ssl/
openssl x509 -in docker/ssl/server.crt -noout -dates
```

**常见原因与解决：**

| 原因 | 解决方案 |
|------|---------|
| 后端未启动 | `docker compose restart backend` |
| WAF 拦截 | 检查 WAF 日志，调整规则 |
| SSL 证书过期 | 续期证书: `certbot renew` |
| Nginx 配置错误 | 检查 `docker/nginx/conf.d/default.conf` |

### 6.3 前端白屏

**现象：** 浏览器访问 `https://<生产域名>/` 显示白屏

**排查步骤：**
```bash
# 1. 检查前端容器
docker logs kb-frontend --tail 50

# 2. 检查 Nginx 代理
curl -k -I https://<生产域名>/

# 3. 浏览器开发者工具
# F12 → Console 查看错误
# F12 → Network 查看请求状态

# 4. 清除浏览器缓存
# Ctrl+Shift+Delete 或无痕模式测试
```

**常见原因与解决：**

| 原因 | 解决方案 |
|------|---------|
| 前端构建失败 | `docker compose up -d --build frontend` |
| API 跨域问题 | 检查 `CORS_ORIGINS` 配置 |
| 浏览器缓存 | 硬刷新 (Ctrl+F5) 或无痕模式 |
| CSP 策略限制 | 检查 Nginx `Content-Security-Policy` 头 |

### 6.4 数据库连接失败

**现象：** 后端日志显示 `Can't connect to MySQL` 或 `Connection refused`

**排查步骤：**
```bash
# 1. 检查数据库容器
docker compose -f docker-compose.prod.yml ps mysql postgres redis

# 2. 测试数据库连接
docker exec kb-mysql mysqladmin ping -u root -p'YOUR_PASSWORD'
docker exec kb-postgres pg_isready -U postgres
docker exec kb-redis redis-cli PING

# 3. 检查网络
docker network inspect enterprise-knowledge-base_kb-network

# 4. 查看数据库日志
docker logs kb-mysql --tail 50
```

**常见原因与解决：**

| 原因 | 解决方案 |
|------|---------|
| 数据库未启动 | `docker compose up -d mysql postgres redis` |
| 密码错误 | 检查 `.env` 中的数据库密码 |
| 网络隔离 | 检查容器是否在同一 network |
| 数据卷损坏 | 从备份恢复（见第 7 节） |

### 6.5 SSL 证书问题

**现象：** 浏览器显示"连接不安全"或证书警告

**排查步骤：**
```bash
# 1. 检查证书文件
ls -la docker/ssl/

# 2. 查看证书详情
openssl x509 -in docker/ssl/server.crt -noout -subject -dates

# 3. 测试 SSL 连接
echo | openssl s_client -connect <生产域名>:443 -servername <生产域名>

# 4. 检查 Nginx 配置
docker exec kb-nginx cat /etc/nginx/conf.d/default.conf | grep ssl
```

**常见原因与解决：**

| 原因 | 解决方案 |
|------|---------|
| 证书过期 | `certbot renew && docker compose restart nginx` |
| 证书路径错误 | 检查 `docker-compose.prod.yml` volumes 挂载 |
| 域名不匹配 | 重新申请证书: `certbot certonly --standalone -d <生产域名>` |
| 自签名证书 | 正常现象，浏览器添加例外即可 |

---

## 7. 回滚流程

### 7.1 镜像回滚

**场景：** 新版本部署后发现问题，需要回滚到上一版本

```bash
# 1. 查看当前镜像
docker images | grep kb-backend

# 2. 标记当前版本为 broken
docker tag kb-backend:latest kb-backend:broken

# 3. 恢复上一版本（deploy.sh 自动保留 previous 标签）
docker tag kb-backend:previous kb-backend:latest

# 4. 重启后端
docker compose -f docker-compose.prod.yml restart backend

# 5. 验证
curl -k https://<生产域名>/api/health
```

### 7.2 数据库回滚

**场景：** 数据库 schema 变更导致问题，需要从备份恢复

```bash
# 1. 停止后端（避免新数据写入）
docker compose -f docker-compose.prod.yml stop backend

# 2. 找到备份文件
ls -la backups/
# 选择最近的备份: backups/YYYYMMDD_HHMMSS/

# 3. 恢复 MySQL
docker compose -f docker-compose.prod.yml exec -T mysql \
  mysql -u root -p'YOUR_PASSWORD' < backups/YYYYMMDD_HHMMSS/mysql_all.sql

# 4. 恢复 PostgreSQL
docker compose -f docker-compose.prod.yml exec -T postgres \
  psql -U postgres langgraph_checkpoint < backups/YYYYMMDD_HHMMSS/postgres_langgraph.sql

# 5. 重启后端
docker compose -f docker-compose.prod.yml start backend

# 6. 验证
curl -k https://<生产域名>/api/health
```

### 7.3 配置回滚

**场景：** 修改 `.env` 后服务异常，需要恢复配置

```bash
# 1. 恢复备份配置
[ -f .env.dev.bak ] && cp .env.dev.bak .env

# 2. 或从 git 恢复
git checkout .env

# 3. 重启服务
docker compose -f docker-compose.prod.yml restart
```

---

## 8. 安全加固建议

### 8.1 密码安全

- [x] 所有数据库密码已使用强随机值（`.env.prod`）
- [ ] 部署后修改默认管理员密码: `admin` / `<默认管理员密码>`
- [ ] 定期轮换 API Key（DeepSeek/企微/公众号）
- [ ] 禁止在代码中硬编码密码

### 8.2 网络安全

- [x] 防火墙仅开放 22/80/443
- [x] 数据库端口不对外暴露（使用 `expose`）
- [ ] 管理后台 IP 白名单（`docker/nginx/conf.d/ip-whitelist.inc`）
- [ ] 启用 HTTPS 强制跳转（已配置）
- [ ] 配置 HSTS（已配置）

### 8.3 应用安全

- [x] `DEBUG=false`（生产模式）
- [x] `LOG_LEVEL=INFO`（避免日志泄露敏感信息）
- [x] CORS 仅允许生产域名
- [ ] 速率限制配置（后端已内置）
- [ ] WAF 规则优化（减少误拦截）
- [ ] 定期更新依赖（`pip list --outdated`）

### 8.4 数据安全

- [x] 定时备份已配置（cron）
- [ ] 备份文件加密存储
- [ ] 异地备份（OSS/S3）
- [ ] 备份恢复演练（每季度一次）

### 8.5 监控告警

- [x] Grafana 看板已配置
- [x] Prometheus 指标采集
- [x] Loki 日志聚合
- [ ] 配置告警规则（邮件/企微通知）
- [ ] 配置 UptimeRobot 外部监控

### 8.6 访问控制

- [ ] 修改 Grafana 默认密码（已完成）
- [ ] 修改 MinIO 默认凭证（已完成）
- [ ] 限制 SSH 访问（密钥登录 + 禁用密码）
- [ ] 配置 fail2ban 防暴力破解
- [ ] 定期审计用户权限

---

## 附录

### A. 默认账号密码

| 系统 | 地址 | 账号 | 密码 |
|------|------|------|------|
| 管理后台 | `https://<生产域名>/app/` | `admin` | `<默认管理员密码>` |
| Grafana | `http://<server-ip>:3000` | `admin` | `.env.prod` 中的 `GRAFANA_PASSWORD` |
| MinIO Console | `http://<server-ip>:9001` | `.env.prod` 中的 `MINIO_ACCESS_KEY` | `.env.prod` 中的 `MINIO_SECRET_KEY` |
| API 文档 | `https://<生产域名>/api/docs` | — | — |

### B. 端口映射

| 端口 | 服务 | 协议 | 对外 |
|------|------|------|------|
| 80 | Nginx HTTP | HTTP | ✅ |
| 443 | Nginx HTTPS | HTTPS | ✅ |
| 8000 | FastAPI 后端 | HTTP | ❌ (仅内网) |
| 3306 | MySQL | MySQL | ❌ (仅内网) |
| 5432 | PostgreSQL | PostgreSQL | ❌ (仅内网) |
| 6379 | Redis | Redis | ❌ (仅内网) |
| 9200 | Elasticsearch | HTTP | ❌ (仅内网) |
| 19530 | Milvus | gRPC | ❌ (仅内网) |
| 9001 | MinIO Console | HTTP | ❌ (仅内网) |
| 3000 | Grafana | HTTP | ❌ (仅内网) |
| 9090 | Prometheus | HTTP | ❌ (仅内网) |

### C. 常用命令速查

```bash
# 查看所有容器
docker ps

# 查看容器日志
docker logs <container_name> --tail 100 -f

# 重启服务
docker compose -f docker-compose.prod.yml restart <service_name>

# 进入容器
docker exec -it <container_name> /bin/bash

# 查看资源占用
docker stats --no-stream

# 备份数据库
bash scripts/backup.sh

# 更新代码
git pull && docker compose -f docker-compose.prod.yml up -d --build
```

### D. 相关文档

- `docs/ops/STARTUP.md` — 启动手册（含故障排查）
- `docs/ops/BACKUP.md` — 备份与恢复指南
- `docs/ops/MONITORING.md` — 监控配置说明
- `docs/ops/TROUBLESHOOTING.md` — 常见问题排查
- `docs/deploy-checklist.md` — 上线验收清单
- `docs/ARCHITECTURE.md` — 系统架构说明

---

## 签字确认

| 角色 | 姓名 | 日期 | 签字 |
|------|------|------|------|
| 部署执行人 | | | |
| 运维负责人 | | | |
| 业务验收人 | | | |

---

> **部署完成后，请逐项验证第 4 节的所有检查项，确保系统正常运行。**
