# 批量文章生成器 — 执行计划

## Context

基于 [详细设计文档](C:\Users\TLD\.claude\plans\velvet-toasting-dream.md) 中的架构设计，结合对现有代码库的全面探索，制定分阶段执行计划。核心原则：后端零修改现有代码，前端完全独立部署，复用现有 LLM/检索/MinIO/认证基础设施。

---

## 阶段一：数据库 + 配置（基础层）

### 1.1 数据库 DDL

**文件**：[docker/mysql/init/01-schema.sql](enterprise-knowledge-base/docker/mysql/init/01-schema.sql)

**操作**：在文件末尾追加 3 张表的 DDL（`article_batch`、`article`、`publishing_record`），遵循现有模式：
- `ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci`
- `created_at DATETIME DEFAULT CURRENT_TIMESTAMP`
- `updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP`
- 外键使用显式约束名

**注意**：现有 MySQL 容器已有数据时需手动 `ALTER TABLE` 或重建 volume。

### 1.2 配置扩展

**文件**：[app/core/config.py](enterprise-knowledge-base/backend/app/core/config.py)

**操作**：在 `Settings` 类末尾（`chat_log_retention_days` 之后）追加新字段：

```python
# 视觉模型（图片分析）
vision_model_provider: str = "openai_compatible"
vision_model_api_key: str = ""
vision_model_name: str = "Qwen/Qwen2-VL-72B-Instruct"
vision_model_base_url: str = "https://api.siliconflow.cn/v1"

# 文章生成
article_default_count: int = 5
article_min_words: int = 500
article_max_words: int = 800
article_temperature: float = 0.8
article_generate_interval: float = 3.0

# 发布
wechatsync_cli_path: str = "wechatsync"
wechat_mp_appid: str = ""
wechat_mp_appsecret: str = ""
```

同步修改 `cors_origins` 的默认值（行88），追加 `http://localhost:5174`。

### 1.3 ORM 模型

**新文件**：[app/articles/__init__.py](enterprise-knowledge-base/backend/app/articles/__init__.py)（空文件）

**新文件**：[app/articles/models.py](enterprise-knowledge-base/backend/app/articles/models.py)

**模式**：完全遵循 [app/models/document.py](enterprise-knowledge-base/backend/app/models/document.py) 的 SQLAlchemy 2.0 `Mapped[]` 风格：
- 继承 `app.core.database.Base`
- `id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)`
- `created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())`
- `updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())`
- 使用 `__table_args__` 定义索引
- JSON 字段用 `JSON` 类型，长文本用 `Text`

3 个模型类：`ArticleBatch`、`Article`、`PublishingRecord`

---

## 阶段二：后端核心模块

### 2.1 Pydantic Schemas

**新文件**：[app/articles/schemas.py](enterprise-knowledge-base/backend/app/articles/schemas.py)

参照 [app/schemas/document.py](enterprise-knowledge-base/backend/app/schemas/document.py) 的 Pydantic v2 模式：
- `BatchCreate`、`BatchResponse`、`BatchDetailResponse`
- `ArticleResponse`、`ArticleUpdate`
- `PublishRequest`、`PublishingRecordResponse`
- `PlatformInfo`
- 复用 [app/schemas/common.py](enterprise-knowledge-base/backend/app/schemas/common.py) 的 `PaginatedResponse`

### 2.2 视觉分析模块

**新文件**：[app/articles/vision.py](enterprise-knowledge-base/backend/app/articles/vision.py)

**设计**：
- 抽象基类 `VisionProvider`（ABC，`analyze(image_base64, prompt) -> str`）
- `OpenAICompatibleVisionProvider`：POST `{base_url}/chat/completions`（OpenAI 兼容视觉 API）
- 工厂函数 `get_vision_provider()` → 根据 `settings` 返回实例
- 主入口 `analyze_photos(photo_object_names, topic) -> str`：
  1. 逐张从 MinIO 下载（复用 `app.core.minio_client.get_minio_client()`）
  2. base64 编码后调用视觉模型
  3. 逐张释放 base64（`del`）避免内存累积
  4. API key 为空时返回占位文本

**依赖**：`httpx`（已在 requirements.txt 中）

### 2.3 文章生成引擎

**新文件**：[app/articles/generator.py](enterprise-knowledge-base/backend/app/articles/generator.py)

**复用**：
- `app.agents.llm.create_llm(temperature, max_tokens)` → 创建 LLM 实例
- `app.agents.llm.call_llm_with_retry(llm, messages)` → 带重试的调用
- `app.retrieval.fusion.hybrid_retrieve(query, scope, top_k)` → 知识检索

**三步流水线**：
1. `_retrieve_knowledge(topic, angles)` → 5 角度 × top-8 检索，存为 `dict[angle_key, list[FusionResult]]`
2. `_plan_angles(topic, photo_descriptions, knowledge_summary)` → LLM 一次调用生成 5 个差异化角度
3. `_generate_articles(batch_id, angles, retrieved_contexts, topic, photo_descriptions)` → 逐篇生成 → 即时写 DB → 释放 → 间隔 3s

**内存安全**（关键）：
- 不累积 5 篇文章在内存中
- 每篇生成完立即 `await save_article_to_db()` + `del article`
- 检索结果仅保留 top-3 传给 LLM

### 2.4 发布服务

**新文件**：[app/articles/publisher.py](enterprise-knowledge-base/backend/app/articles/publisher.py)

**三层发布能力**：
1. **微信公众号草稿 API**：`POST https://api.weixin.qq.com/cgi-bin/draft/add`，access_token 缓存到 Redis（复用现有 `RedisCache`，TTL 7000s）
2. **Wechatsync CLI**：`asyncio.create_subprocess_exec("wechatsync", "publish", ...)`，发布到草稿箱
3. **文件导出**：`python-docx`（已在 requirements.txt 中）生成 DOCX，Markdown/HTML 直接返回

平台注册表（9个平台）作为类常量。

### 2.5 业务服务层

**新文件**：[app/articles/service.py](enterprise-knowledge-base/backend/app/articles/service.py)

**模式**：遵循 [app/services/document_service.py](enterprise-knowledge-base/backend/app/services/document_service.py) 的 `class Service: def __init__(self, db: AsyncSession)` 模式。

**核心方法**：
- `create_batch(topic, user_id) -> ArticleBatch`
- `upload_photos(batch_id, files) -> list[str]`（MinIO object names）
- `start_generation(batch_id)` → `asyncio.create_task(_run_generation(batch_id))`（后台任务）
- `get_batch(batch_id) -> BatchDetailResponse`
- `list_batches(user_id, page, page_size) -> PaginatedResponse`
- `update_article(article_id, title, content) -> Article`
- `regenerate_article(article_id) -> Article`
- `delete_batch(batch_id)`
- `publish_articles(batch_id, platform_ids, article_ids) -> dict`
- `export_article(article_id, format) -> bytes`
- `export_batch_zip(batch_id) -> bytes`

---

## 阶段三：API 路由 + 注册

### 3.1 REST API 端点

**新文件**：[app/api/articles.py](enterprise-knowledge-base/backend/app/api/articles.py)

**模式**：完全遵循 [app/api/admin/document.py](enterprise-knowledge-base/backend/app/api/admin/document.py) 的路由模式：
- `router = APIRouter(prefix="/articles", tags=["admin-articles"])`
- 使用 `DbDep`、`require_auth`、`require_permission("write")` 依赖注入
- 分页参数 `page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100)`
- 错误处理：`try/except ValueError as e` → `HTTPException(400)`

**15 个端点**（与设计文档一致）：
- `POST /batches` — 创建批次
- `POST /batches/{id}/upload-photos` — 上传照片（FormData，复用 MinIO 上传模式）
- `POST /batches/{id}/generate` — 启动后台生成
- `GET /batches/{id}/stream` — SSE 实时进度（参照 `app/api/agent/__init__.py` 的 StreamingResponse 模式）
- `GET /batches/{id}` — 批次详情
- `GET /batches` — 批次列表
- `DELETE /batches/{id}` — 删除
- `GET /articles/{id}` — 文章详情
- `PUT /articles/{id}` — 编辑
- `POST /articles/{id}/regenerate` — 重生成
- `POST /articles/{id}/publish` — 发布单篇
- `POST /batches/{id}/publish` — 批量发布
- `GET /articles/{id}/publishing-status` — 发布状态
- `GET /platforms` — 平台列表
- `GET /articles/{id}/export` / `GET /batches/{id}/export` — 导出

### 3.2 路由注册

**文件**：[app/api/admin/__init__.py](enterprise-knowledge-base/backend/app/api/admin/__init__.py)

**操作**：追加两行：
```python
from app.api.articles import router as articles_router
# ...
router.include_router(articles_router)
```

---

## 阶段四：后端测试

### 4.1 单元测试

**新文件**：[tests/unit/test_article_generator.py](enterprise-knowledge-base/backend/tests/unit/test_article_generator.py)
- Mock `create_llm` 和 `hybrid_retrieve`
- 验证角度规划返回 5 个差异化角度
- 验证单篇文章生成格式正确

**新文件**：[tests/unit/test_article_vision.py](enterprise-knowledge-base/backend/tests/unit/test_article_vision.py)
- Mock httpx 响应
- 验证 base64 编码 + API 调用流程
- 验证 API key 为空时的降级行为

**新文件**：[tests/unit/test_article_publisher.py](enterprise-knowledge-base/backend/tests/unit/test_article_publisher.py)
- 验证 DOCX 导出产物可被 `python-docx` 打开
- Mock subprocess 验证 CLI 参数

### 4.2 集成测试

**新文件**：[tests/integration/test_articles_api.py](enterprise-knowledge-base/backend/tests/integration/test_articles_api.py)
- 遵循 [tests/integration/test_feedback_flow.py](enterprise-knowledge-base/backend/tests/integration/test_feedback_flow.py) 模式
- 使用 SQLite 内存数据库 + `httpx.AsyncClient` + `ASGITransport`
- 测试完整 CRUD 链路：创建批次 → 上传照片 → 启动生成 → 查询文章 → 编辑 → 删除
- 验证权限控制（readonly 用户不能创建批次）

---

## 阶段五：独立前端应用

### 5.1 项目初始化

在 `enterprise-knowledge-base/` 同级创建 `article-generator/`：

```bash
npm create vite@latest article-generator -- --template vue-ts
cd article-generator
npm install element-plus @element-plus/icons-vue vue-router@4 pinia@2 axios markdown-it
```

**Vite 配置**：`server.port = 5174`，`proxy: {"/api": "http://localhost:8000"}`（本地开发用）

### 5.2 认证模块

**新文件**：[src/stores/auth.ts](article-generator/src/stores/auth.ts) — 镜像现有 [frontend/src/stores/auth.ts](enterprise-knowledge-base/frontend/src/stores/auth.ts)，只保留 `token`/`user`/`isLoggedIn`/`doPhoneLogin`/`init`/`logout`/`getToken`

**新文件**：[src/api/auth.ts](article-generator/src/api/auth.ts) — 调用 `/api/admin/auth/login` 和 `/api/admin/auth/me`

**新文件**：[src/router/index.ts](article-generator/src/router/index.ts) — hash history + auth guard，5 条路由

**新文件**：[src/views/Login.vue](article-generator/src/views/Login.vue) — 镜像现有 Login.vue

### 5.3 API 客户端

**新文件**：[src/api/articles.ts](article-generator/src/api/articles.ts)
- 遵循现有 [frontend/src/api/document.ts](enterprise-knowledge-base/frontend/src/api/document.ts) 的 `fetch` + `h()` helper 模式
- `BASE = "/api/admin/articles"`
- 15 个 API 函数 + SSE `subscribeBatchProgress()`

### 5.4 核心页面 — Generator.vue

**新文件**：[src/views/Generator.vue](article-generator/src/views/Generator.vue)

单页完成三步流程：
1. 输入主题 → 创建批次
2. 上传照片（拖拽区 + 缩略图预览 + 前端 canvas 压缩至 1920px/2MB）
3. 点击生成 → SSE 实时进度条 → 5 篇文章卡片渐次出现

### 5.5 其他页面 + 组件

| 文件 | 复杂度 | 说明 |
|------|--------|------|
| `views/ArticleEdit.vue` | 中 | 左编辑右预览（markdown-it），字数统计 |
| `views/BatchHistory.vue` | 低 | 分页表格（Element Plus `el-table`） |
| `views/PublishManager.vue` | 中 | 平台网格 + 批量发布 + 导出按钮 |
| `components/PhotoUploader.vue` | 中 | 拖拽上传 + canvas 压缩 + 缩略图 |
| `components/ArticleCard.vue` | 低 | 标题/摘要/操作按钮卡片 |
| `components/ProgressTracker.vue` | 低 | SSE 驱动的进度条 |
| `components/PlatformSelector.vue` | 低 | 平台多选框 |
| `components/MarkdownPreview.vue` | 低 | markdown-it 渲染 |
| `components/ExportPanel.vue` | 低 | 格式选择 + 下载触发 |

### 5.6 Docker 化

**新文件**：[article-generator/Dockerfile](article-generator/Dockerfile)
- 模式：参照 [frontend/docker/Dockerfile](enterprise-knowledge-base/frontend/docker/Dockerfile)
- 三阶段：base → dev → production（nginx:1.27-alpine 静态服务）

**新文件**：[article-generator/docker/nginx-frontend.conf](article-generator/docker/nginx-frontend.conf)
- 参照 [frontend/docker/nginx-frontend.conf](enterprise-knowledge-base/frontend/docker/nginx-frontend.conf)
- SPA fallback + asset caching

---

## 阶段六：Docker 集成

### 6.1 Docker Compose

**文件**：[docker-compose.yml](enterprise-knowledge-base/docker-compose.yml)

**操作**：新增 `article-generator` 服务（dev target, expose 5174, 挂载源码 volume, 加入 kb-network）

### 6.2 Nginx 配置

**文件**：[docker/nginx/conf.d/default.conf](enterprise-knowledge-base/docker/nginx/conf.d/default.conf)

**操作**：新增 `upstream article_generator` + 条件路由（可选，按 Host header 或路径前缀区分）

---

## 阶段七：端到端验证

1. `docker compose up -d` 启动全部服务
2. 访问 `http://localhost:5174` → 登录 → 输入题目 → 上传 3 张照片 → 生成
3. 验证 5 篇文章标题不同、字数 500-800、含知识库专业术语
4. 验证现有系统 `:5173` 功能正常（零回归）
5. 验证 DOCX 导出可用、SSE 进度实时更新
6. 运行 `pytest backend/tests/ -k article` 全部通过

---

## 文件清单

### 新建文件（~21 个）

| # | 文件 | 阶段 |
|---|------|------|
| 1 | `backend/app/articles/__init__.py` | 1 |
| 2 | `backend/app/articles/models.py` | 1 |
| 3 | `backend/app/articles/schemas.py` | 2 |
| 4 | `backend/app/articles/vision.py` | 2 |
| 5 | `backend/app/articles/generator.py` | 2 |
| 6 | `backend/app/articles/publisher.py` | 2 |
| 7 | `backend/app/articles/service.py` | 2 |
| 8 | `backend/app/api/articles.py` | 3 |
| 9 | `backend/tests/unit/test_article_generator.py` | 4 |
| 10 | `backend/tests/unit/test_article_vision.py` | 4 |
| 11 | `backend/tests/unit/test_article_publisher.py` | 4 |
| 12 | `backend/tests/integration/test_articles_api.py` | 4 |
| 13 | `article-generator/` (Vite 项目 + 全部源文件) | 5 |
| 14 | `article-generator/Dockerfile` | 5 |
| 15 | `article-generator/docker/nginx-frontend.conf` | 5 |

### 修改文件（5 个）

| # | 文件 | 变更 | 阶段 |
|---|------|------|------|
| 1 | `docker/mysql/init/01-schema.sql` | 追加 3 张表 DDL | 1 |
| 2 | `backend/app/core/config.py` | 追加 10 个字段 + 修改 `cors_origins` 默认值 | 1 |
| 3 | `backend/app/api/admin/__init__.py` | 追加 2 行 import + include_router | 3 |
| 4 | `docker-compose.yml` | 新增 article-generator 服务 | 6 |
| 5 | `docker/nginx/conf.d/default.conf` | 新增 upstream + location | 6 |

---

## 依赖关系图

```
阶段一 (DB+Config+Models) ──┐
                            ├──→ 阶段二 (Schemas→Vision→Generator→Publisher→Service)
                            │         │
                            │         └──→ 阶段三 (API Routes → 注册) ──→ 阶段四 (测试)
                            │
                            └──→ 阶段五 (前端项目 → 认证 → API客户端 → 页面组件 → Docker化)
                                                                              │
                                                                              └──→ 阶段六 (Docker集成)
                                                                                        │
                                                                                        └──→ 阶段七 (验证)
```

**关键路径**：阶段一 → 阶段二（Generator）→ 阶段三 → 验证。这是最早可 demo 的路径。
**并行机会**：阶段五（前端）可与阶段二~四（后端）完全并行开发，因为 API 契约已在阶段三定义。
