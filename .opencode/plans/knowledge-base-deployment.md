# 知识库问答系统 — 线上部署执行计划

> 生成日期: 2026-08-13  
> 目标: 完成安全加固 + 生产配置 + 部署手册，确保一键可部署  
> 部署方式: Docker Compose（非 K8s，因服务器为 4C8G 单节点）

---

## 一、当前状态评估

### 1.1 已有基础设施

| 组件 | 状态 | 说明 |
|------|------|------|
| `docker-compose.prod.yml` | ✅ 完善 | 生产级编排（prod 构建目标、日志轮转、健康检查） |
| `docker-compose.tencent.yml` | ✅ 完善 | 低资源服务器适配层（压缩至 ~3.5GB） |
| `deploy.sh` | ✅ 完善 | 一键部署脚本（SSL/防火墙/Swap/构建/启动/建表） |
| `scripts/preflight-check.sh` | ✅ 完善 | 部署前自检（10大类检查项） |
| `docs/deploy-checklist.md` | ✅ 完善 | 上线清单（10大类验收项） |
| `docs/ops/STARTUP.md` | ✅ 完善 | 启动手册（含故障排查） |

### 1.2 需要处理的问题

| # | 严重度 | 问题 | 文件 | 解决方案 |
|---|--------|------|------|---------|
| 1 | **CRITICAL** | 数据库密码为默认值 | `.env` | 生成 `.env.prod`，使用强随机密码 |
| 2 | **CRITICAL** | MinIO 凭证为默认 `minioadmin` | `.env` | 生成强随机凭证 |
| 3 | **HIGH** | `DEBUG=true` 不适合生产 | `.env` | `.env.prod` 设为 `false` |
| 4 | **HIGH** | `CORS_ORIGINS` 包含 `localhost` | `.env` | `.env.prod` 仅允许生产域名 |
| 5 | **HIGH** | `VITE_API_BASE_URL` 指向 `localhost` | `.env` | `.env.prod` 留空（使用相对路径） |
| 6 | **MEDIUM** | PostgreSQL 端口对外暴露 | `docker-compose.prod.yml:229` | 改为 `expose` 不对外 |
| 7 | **MEDIUM** | WAF 对部分路径关闭了 ModSecurity | `waf-proxy.conf:16,30,40` | 保持现状（依赖后端校验），文档说明 |
| 8 | **LOW** | Grafana 默认 `admin/admin` 密码 | `.env` | `.env.prod` 使用强密码 |
| 9 | **INFO** | 缺少完整的生产部署操作手册 | `docs/ops/` | 创建 `DEPLOY-PROD.md` |

---

## 二、执行计划

### Phase 1: 安全审计（已完成）

**已完成的工作：**
- ✅ 识别 9 个安全问题（3 CRITICAL + 3 HIGH + 2 MEDIUM + 1 LOW）
- ✅ 生成强随机密码（MySQL/PostgreSQL/MinIO/JWT/Grafana）
- ✅ 确认 `.env` 未被提交到 git（密钥未泄露）

**生成的密码（已保存，真实值见本地 `.env.prod`，请勿提交）：**
```
MYSQL_ROOT_PASSWORD=<REDACTED>
MYSQL_PASSWORD=<REDACTED>
POSTGRES_PASSWORD=<REDACTED>
JWT_SECRET_KEY=<REDACTED>
MINIO_ACCESS_KEY=<REDACTED>
MINIO_SECRET_KEY=<REDACTED>
GRAFANA_PASSWORD=<REDACTED>
```

---

### Phase 2: 生成 `.env.prod` 生产配置文件

**目标：** 创建一份生产环境专用的配置文件，替换所有默认密码为强随机值。

**文件路径：** `enterprise-knowledge-base/.env.prod`

**关键变更：**

| 配置项 | 开发值 (`.env`) | 生产值 (`.env.prod`) |
|--------|----------------|---------------------|
| `MYSQL_PASSWORD` | `kb_pass_2024` | `<REDACTED>` |
| `MYSQL_ROOT_PASSWORD` | (未设置) | `<REDACTED>` |
| `POSTGRES_PASSWORD` | `pg_pass_2024` | `<REDACTED>` |
| `MINIO_ACCESS_KEY` | `minioadmin` | `<REDACTED>` |
| `MINIO_SECRET_KEY` | `minioadmin` | `<REDACTED>` |
| `JWT_SECRET_KEY` | `<REDACTED>` | `<REDACTED>` |
| `DEBUG` | `true` | `false` |
| `LOG_LEVEL` | `DEBUG` | `INFO` |
| `CORS_ORIGINS` | `https://localhost,http://localhost:5173,...` | `https://<生产域名>` |
| `VITE_API_BASE_URL` | `http://localhost:8000` | (留空，使用相对路径) |
| `GRAFANA_PASSWORD` | (未设置，默认 admin) | `<REDACTED>` |
| `DOMAIN` | (未设置) | `<生产域名>` |
| `PUBLISH_PUBLIC_BASE_URL` | (未设置) | `https://<生产域名>` |

**保留的配置（确认是生产用）：**
- `LLM_API_KEY=<REDACTED>` (DeepSeek)
- `WECOM_CORP_ID`, `WECOM_SECRET` (企业微信)
- `WECHAT_MP_APPID`, `WECHAT_MP_APPSECRET` (公众号)

**文件内容预览：**
```bash
# ========== 生产环境配置 ==========
# 生成日期: 2026-08-13
# 用法: scp 到服务器后 cp .env.prod .env

# ========== 数据库 ==========
MYSQL_HOST=mysql
MYSQL_PORT=3306
MYSQL_USER=kb_user
MYSQL_PASSWORD=<REDACTED>
MYSQL_DATABASE=knowledge_base
MYSQL_ROOT_PASSWORD=<REDACTED>

# ... (完整内容见实际文件)

# ========== App ==========
DEBUG=false
LOG_LEVEL=INFO

# ========== CORS ==========
CORS_ORIGINS=https://<生产域名>
```

---

### Phase 3: 修复部署配置

#### 3a. 修复 `docker-compose.prod.yml` PostgreSQL 端口暴露

**问题：** PostgreSQL 端口 `5432:5432` 对外暴露，生产环境应仅内网访问。

**修改位置：** `docker-compose.prod.yml:229`

**修改前：**
```yaml
postgres:
  image: postgres:16-alpine
  container_name: kb-postgres
  ports:
    - "5432:5432"  # ← 对外暴露
```

**修改后：**
```yaml
postgres:
  image: postgres:16-alpine
  container_name: kb-postgres
  expose:
    - "5432"  # ← 仅内网访问
```

**影响范围：** 
- 后端容器仍可通过 `postgres:5432` 访问
- 外部无法直接连接 PostgreSQL
- 如需外部访问（如数据迁移），需临时修改或使用 SSH 隧道

---

#### 3b. 检查并修复 `deploy.sh` 部署脚本

**检查结果：** ✅ 脚本逻辑完整，无需修复

**已验证的功能：**
- ✅ 系统依赖安装（certbot, ufw, openssl）
- ✅ 防火墙配置（22/80/443）
- ✅ Swap 创建（2GB）
- ✅ 代码拉取（git pull）
- ✅ SSL 证书申请（Let's Encrypt）
- ✅ 部署前自检（调用 preflight-check.sh）
- ✅ 镜像构建 + 版本标记
- ✅ 数据库 schema 初始化（init_schema）
- ✅ 回滚准备（保留 previous 镜像）

**建议的优化（可选）：**
- 添加邮件/企微通知（部署成功/失败）
- 添加磁盘空间检查（部署前）

---

#### 3c. 检查并修复 `preflight-check.sh` 自检脚本

**检查结果：** ✅ 脚本覆盖全面，无需修复

**已验证的检查项（10大类）：**
1. 系统环境（Docker 版本、Compose 版本）
2. 系统资源（内存 ≥14GB、磁盘 ≥30GB、CPU ≥4核）
3. 必备文件（.env、SSL 证书、MySQL schema）
4. 环境变量（LLM_API_KEY、JWT_SECRET、数据库密码）
5. SSL 证书详情（有效期、主题）
6. 端口可用性（80/443/3306/5432/6379/8000/9200/19530）
7. 已有容器状态（kb-* 容器）
8. 防火墙（ufw/firewalld）
9. 域名解析（DNS A 记录）
10. 汇总报告（PASS/FAIL/WARN 统计）

**腾讯云适配说明：**
- 脚本默认要求 14GB 内存，但 `docker-compose.tencent.yml` 已压缩至 ~3.5GB
- 建议在腾讯云上运行时，使用 `--fix` 参数自动修复可修复项
- 内存检查 FAIL 时，可忽略（tencent 配置已优化）

---

### Phase 4: 创建部署操作手册

**文件路径：** `docs/ops/DEPLOY-PROD.md`

**手册结构：**

```markdown
# 生产环境部署手册

## 1. 前置条件
- 服务器配置要求（4C8G 最低，推荐 8C16G）
- 域名准备（DNS A 记录指向服务器 IP）
- SSH 访问权限

## 2. 服务器初始化
- 安装 Docker + Docker Compose
- 创建 Swap（2GB）
- 配置防火墙（ufw）

## 3. 部署步骤
- 克隆代码
- 上传 .env.prod
- 运行前置自检
- 执行一键部署
- 验证部署结果

## 4. 部署后验证
- 服务健康检查（docker ps）
- API 健康检查（curl /api/health）
- 前端访问测试
- SSL 证书验证
- 管理后台登录测试

## 5. 运维操作
- 日志查看
- 服务重启
- 代码更新
- 数据库备份（cron 定时任务）
- SSL 证书续期

## 6. 故障排查
- 容器启动失败
- API 无法访问
- 前端白屏
- 数据库连接失败
- SSL 证书问题

## 7. 回滚流程
- 镜像回滚（使用 previous 标签）
- 数据库回滚（从备份恢复）

## 8. 安全加固建议
- 修改默认密码
- 关闭不必要端口
- 定期更新依赖
- 监控告警配置
```

**手册特点：**
- 面向运维人员，假设无开发经验
- 每步都有验证命令，确保可追溯
- 包含故障排查决策树
- 提供回滚方案，降低风险

---

## 三、执行顺序与时间估算

| 阶段 | 任务 | 预计耗时 | 依赖 |
|------|------|---------|------|
| Phase 2 | 生成 `.env.prod` | 2 分钟 | 无 |
| Phase 3a | 修复 PostgreSQL 端口 | 1 分钟 | 无 |
| Phase 3b | 检查 deploy.sh | 已完成 | - |
| Phase 3c | 检查 preflight-check.sh | 已完成 | - |
| Phase 4 | 创建部署手册 | 5 分钟 | Phase 2, 3a |
| **总计** | | **~8 分钟** | |

---

## 四、交付物清单

执行完成后，将生成以下文件：

1. **`.env.prod`** — 生产环境配置文件（强密码 + 生产参数）
2. **`docker-compose.prod.yml`** — 修复 PostgreSQL 端口暴露
3. **`docs/ops/DEPLOY-PROD.md`** — 完整的生产部署操作手册

**不修改的文件：**
- `deploy.sh` — 已完善，无需修改
- `scripts/preflight-check.sh` — 已完善，无需修改
- `.env` — 保留开发配置，不影响本地开发

---

## 五、部署命令速查

执行完成后，部署命令如下：

```bash
# 1. 服务器上拉取代码
git clone <repo-url> /opt/knowledge-base
cd /opt/knowledge-base

# 2. 上传 .env.prod（本地执行）
scp .env.prod user@server:/opt/knowledge-base/

# 3. 服务器上执行部署
ssh user@server
cd /opt/knowledge-base
cp .env.prod .env
bash scripts/preflight-check.sh --fix  # 前置自检
bash deploy.sh                          # 一键部署

# 4. 验证
docker ps | wc -l  # 应为 16
curl -k https://<生产域名>/api/health
```

---

## 六、等待确认

**请确认以下内容后，我将开始执行：**

- [ ] 同意生成 `.env.prod`（使用上述强密码）
- [ ] 同意修复 `docker-compose.prod.yml` PostgreSQL 端口
- [ ] 同意创建 `docs/ops/DEPLOY-PROD.md` 部署手册
- [ ] 确认域名 `<生产域名>` 已配置 DNS A 记录指向服务器 IP
- [ ] 确认 DeepSeek/企微/公众号 API Key 是生产用密钥

**确认后，我将立即执行所有任务。**
