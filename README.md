# 企业知识库系统（Enterprise Knowledge Base）

基于 **RAG + LangGraph** 的企业级智能问答与内容运营平台，面向内部员工与外部客户提供
知识问答、客服智能体、多源内容采集、AI 写作与多渠道发布能力。

- **内部智能体**：面向员工，检索 `public + internal` 知识，支持 FAQ 短路、混合检索、工具调用（ReAct）。
- **客服智能体**：面向外部客户，检索 `public + customer` 知识，支持 4 类转人工触发。
- **内容运营**：多源采集（公众号 / 头条 / 知乎 / B站 / 官网）、AI 写作、照片库、模板、多渠道发布。
- **三重安全隔离**：向量层（Collection 隔离）、路由层（scope 裁剪）、接口层（JWT + API Key 鉴权）。

---

## 技术栈

| 层 | 技术 |
|---|---|
| 后端 | Python 3.11 · FastAPI · LangGraph · SQLAlchemy · Alembic |
| 前端（用户端） | Vue 3 · Element Plus · Vite |
| 前端（管理后台） | React 18 · TypeScript · Vite · Tailwind CSS · shadcn/ui |
| 发布桥接 | Node.js（Markdown → HTML、发布 API） |
| 大模型 | DeepSeek（可替换任意 OpenAI 兼容 API） |
| 向量 / 重排 | BAAI/bge-large-zh-v1.5（1024 维）· BAAI/bge-reranker-v2-m3 |
| 向量库 | Milvus 2.4 |
| 全文检索 | Elasticsearch 8.15（BM25 + RRF 融合） |
| 关系库 | MySQL 8.0（业务）· PostgreSQL 16（LangGraph Checkpoint） |
| 缓存 / 存储 | Redis 7 · MinIO |
| 网关 / 安全 | Nginx 1.27 · ModSecurity WAF（OWASP CRS） |
| 可观测性 | Prometheus · Grafana · Loki · Promtail |
| 部署 | Docker Compose（15 个服务） |

---

## 目录结构

```
zhshku-main/
├── README.md
├── .gitignore
├── models/                       # 模型挂载目录（部署时下载，见下方说明）
└── enterprise-knowledge-base/
    ├── backend/                  # FastAPI 后端
    │   ├── app/                  # 应用代码（app/models 为 SQLAlchemy ORM 模型）
    │   ├── alembic/              # 数据库迁移
    │   ├── ocr_models/           # RapidOCR 模型（*.onnx 未纳入仓库）
    │   ├── scripts/              # 后端运维脚本
    │   ├── tests/                # 单元 / 集成 / E2E 测试
    │   └── requirements.txt
    ├── frontend/                 # Vue 3 用户端 SPA
    ├── app/                      # React + Vite 管理后台
    ├── publisher-bridge/         # Node.js 发布桥接服务（浏览器扩展后端）
    ├── docker/                   # nginx / mysql / grafana / loki / prometheus / waf / ssl
    ├── scripts/                  # 部署 / 自检 / 备份脚本
    ├── docs/                     # 架构、运维、测试、开发日志（见文档索引）
    ├── docker-compose.yml        # 开发编排
    ├── docker-compose.prod.yml   # 生产编排
    ├── docker-compose.tencent.yml# 低配服务器适配层
    ├── deploy.sh                 # 一键生产部署（SSL/防火墙/Swap/构建/建表）
    ├── start.ps1                 # Windows 一键启动 + 自检
    └── .env.example              # 环境变量模板
```

---

## 快速开始

### 1. 准备环境变量

```bash
cd enterprise-knowledge-base
cp .env.example .env
# 编辑 .env，至少配置 LLM_API_KEY（DeepSeek 或兼容 API）
```

### 2. 启动（二选一）

**方式 A：Windows 一键脚本（推荐，含健康检查与业务自检）**

```powershell
cd enterprise-knowledge-base
.\start.ps1
```

**方式 B：Docker Compose 手动启动**

```bash
cd enterprise-knowledge-base
docker compose up -d
# 等待容器 healthy 后初始化数据库
docker compose exec backend python -m app.scripts.init_schema
```

### 3. 访问入口

> 统一通过 HTTPS 入口访问，避免直接使用原始端口导致缓存/跨域问题。

| 入口 | 地址 |
|---|---|
| 用户端（Vue） | https://localhost |
| 管理后台（React） | https://localhost/app/ |
| API 健康检查 | https://localhost/api/health |
| API 文档 | https://localhost/api/docs |
| Grafana 监控 | http://localhost:3000 |

---

## 服务与端口

| 容器 | 端口 | 说明 |
|---|---|---|
| kb-nginx | 80 / 443 | 反向代理 + HTTPS |
| kb-waf | 8080 | ModSecurity WAF 代理 |
| kb-backend | 8000 | FastAPI |
| kb-frontend | 5173 | Vue + React 合并构建 |
| kb-mysql | 3306 | 业务库 |
| kb-postgres | 5432 | LangGraph Checkpoint |
| kb-redis | 6379 | 缓存 / Session |
| kb-es | 9200 | BM25 全文检索 |
| kb-milvus | 19530 | 向量检索 |
| kb-etcd | 2379 | Milvus 元数据 |
| kb-minio | 9000 | 对象存储 |
| kb-prometheus | 9090 | 指标采集 |
| kb-grafana | 3000 | 监控看板 |
| kb-loki | 3100 | 日志聚合 |
| kb-promtail | — | 日志采集 |

---

## OCR 模型说明

`backend/ocr_models/*.onnx`（约 15.5 MB）因体积原因**未纳入仓库**。扫描版 PDF 兜底识别
使用 [RapidOCR](https://github.com/RapidAI/RapidOCR)（PP-OCRv4 mobile，CPU onnxruntime）。
运行前需将以下模型放入 `enterprise-knowledge-base/backend/ocr_models/`：

```
ch_PP-OCRv4_det_mobile.onnx
ch_PP-OCRv4_rec_mobile.onnx
ch_ppocr_mobile_v2.0_cls_mobile.onnx
```

获取方式（任选其一）：

- 从 [RapidOCR 官方发布](https://github.com/RapidAI/RapidOCR/releases) / 模型仓库下载对应 PP-OCRv4 mobile onnx；
- 或安装 `rapidocr-onnxruntime` 后，从其包内置模型目录复制。

`rapidocr_cfg.yaml` 已在仓库中，配置的 `model_path` 指向 `/app/ocr_models/`。
未提供模型时，非扫描版文档解析不受影响，仅扫描版 PDF 的 OCR 兜底不可用。

---

## 环境变量

完整变量清单见 `enterprise-knowledge-base/.env.example`，关键项：

| 变量 | 说明 |
|---|---|
| `LLM_API_KEY` / `LLM_MODEL` / `LLM_BASE_URL` | 大模型接入（默认 DeepSeek） |
| `MYSQL_*` / `POSTGRES_*` / `REDIS_*` | 数据库与缓存连接 |
| `MILVUS_*` / `ES_*` / `MINIO_*` | 检索与对象存储 |
| `JWT_SECRET_KEY` | JWT 签名密钥（生产务必改为强随机值） |
| `SILICONFLOW_API_KEY` | 云端 Embedding / Reranker（可选） |
| `WECOM_*` / `TENCENT_*` | 企业微信渠道与语音识别（可选） |
| `WECHAT_MP_*` / `TOUTIAO_*` / `ZHIHU_*` / `BILIBILI_*` | 多源内容采集（可选） |
| `DOMAIN` / `GRAFANA_*` | 部署域名与监控账号 |

> `.env` 已被 `.gitignore` 排除，请勿提交任何真实密钥。

---

## 生产部署

```bash
# 服务器上
git clone <你的仓库地址> /opt/knowledge-base
cd /opt/knowledge-base/enterprise-knowledge-base
cp .env.prod .env                 # 生产配置（含强随机密码）
bash scripts/preflight-check.sh   # 部署前自检
bash deploy.sh                    # 一键部署：SSL + 防火墙 + Swap + 构建 + 建表
```

详见 `docs/ops/DEPLOY-PROD.md`、`docs/deploy-checklist.md`、`docs/ops/STARTUP.md`。

---

## 文档索引

| 文档 | 内容 |
|---|---|
| `docs/ARCHITECTURE.md` | 系统架构图与核心数据流 |
| `docs/LANGGRAPH_NODES.md` | LangGraph 节点说明 |
| `docs/ops/DEPLOY-PROD.md` | 生产部署手册 |
| `docs/ops/STARTUP.md` / `TROUBLESHOOTING.md` | 启动与故障排查 |
| `docs/ops/MONITORING.md` / `BACKUP.md` / `ROLLBACK.md` | 监控 / 备份 / 回滚 |
| `docs/ops/USER_GUIDE.md` | 用户使用指南 |
| `docs/`（开发日志） | 按日期的开发与调试记录 |

---

## 安全说明

- 仓库内**不包含**任何生产密钥、SSL 私钥与数据库密码；相关文档已脱敏为占位符。
- `.env`、`docker/ssl/`、`backend/data/`、`backend/models_cache/`、`*.onnx` 等已在 `.gitignore` 中排除。
- 上线后请立即修改默认管理员密码，并在企微后台重置应用 Secret。
