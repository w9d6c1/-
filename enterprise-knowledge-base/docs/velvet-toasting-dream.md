# 批量文章生成器 — 详细实施计划

## Context

用户从事电渗透防潮防水业务，需要批量生产 GEO（生成式引擎优化）文章。核心需求：输入一个题目 + 3~5 张现场照片 → 调用知识库知识 → 一次生成 5 篇内容各异的文章（同题不同角度/风格，500~800 字）→ 一键发布到多平台或导出文件。前端需完全独立于现有项目，不影响原系统使用。

## 总体架构

```
[独立前端 :5174] ──→ [Nginx] ──→ [FastAPI Backend :8000]
                                      │
                    ┌─────────────────┼─────────────────┐
                    │                 │                 │
              [文章生成服务]    [知识检索(复用)]   [发布/导出服务]
                    │                 │                 │
              DeepSeek LLM      Milvus + ES       Wechatsync CLI
              + 视觉模型          RRF融合          + 公众号API
              (图片分析)                          + DOCX导出
```

**关键原则**：
- 后端只新增模块，**零修改**现有代码
- 前端完全独立部署，不同端口，**互不影响**
- 复用现有 MinIO（图片存储）、检索管道（知识召回）、LLM 配置、数据库会话

---

## 一、后端模块详细设计

### 1.1 新目录结构

```
enterprise-knowledge-base/
  backend/app/
    api/
      articles.py                      # NEW: REST API 路由 (/api/admin/articles)
    articles/                          # NEW: 文章模块
      __init__.py
      models.py                        # ArticleBatch + Article + PublishingRecord ORM
      schemas.py                       # Pydantic 请求/响应
      service.py                       # 业务逻辑：CRUD + 后台任务调度
      generator.py                     # 文章生成引擎（核心）
      publisher.py                     # 发布集成（Wechatsync CLI + 公众号 API）
      vision.py                        # 图片分析（多模态视觉模型）
    agents/
      article_graph.py                 # NEW: LangGraph 文章生成管道
      article_state.py                 # NEW: 文章生成状态定义
      nodes/
        article_retrieve.py            # NEW: 知识检索节点
        article_generate.py            # NEW: 批量文章生成节点
        article_evaluate.py            # NEW: 质量评估节点
```

### 1.2 数据库表设计（MySQL）

**`article_batch`** — 批量生成任务

| 字段 | 类型 | 说明 |
|------|------|------|
| id | INT PK AUTO_INCREMENT | 批次 ID |
| topic | VARCHAR(500) NOT NULL | 用户输入的题目 |
| photo_count | INT DEFAULT 0 | 上传照片数量 |
| photo_object_names | JSON DEFAULT NULL | MinIO object names 数组 |
| photo_descriptions | LONGTEXT DEFAULT NULL | 视觉模型分析结果汇总 |
| article_count | INT DEFAULT 5 | 目标文章数 |
| generated_count | INT DEFAULT 0 | 已生成篇数 |
| status | ENUM('draft','generating','completed','failed') | 批次状态 |
| error_message | TEXT DEFAULT NULL | 失败原因 |
| user_id | INT NOT NULL | 创建者 |
| created_at | DATETIME | |
| updated_at | DATETIME | |

**`article`** — 单篇文章

| 字段 | 类型 | 说明 |
|------|------|------|
| id | INT PK AUTO_INCREMENT | |
| batch_id | INT FK NOT NULL | 关联批次 |
| title | VARCHAR(500) NOT NULL | 生成的文章标题 |
| content | LONGTEXT NOT NULL | 文章正文（Markdown） |
| word_count | INT DEFAULT 0 | 字数 |
| angle | VARCHAR(100) NOT NULL | 角度标签（technical / case_study / benefits / comparison / maintenance） |
| image_placement | JSON DEFAULT NULL | 配图在文章中的位置 `[{object_name, caption, position}]` |
| status | ENUM('draft','published','exported') DEFAULT 'draft' | |
| review_status | ENUM('pending','approved','rejected') DEFAULT 'pending' | |
| user_id | INT | 创建者 |
| created_at | DATETIME | |
| updated_at | DATETIME | |

**`publishing_record`** — 发布记录

| 字段 | 类型 | 说明 |
|------|------|------|
| id | INT PK AUTO_INCREMENT | |
| article_id | INT FK NOT NULL | |
| platform | VARCHAR(50) NOT NULL | 平台标识 |
| platform_name | VARCHAR(100) | 平台显示名 |
| status | ENUM('pending','published','failed') | |
| published_url | VARCHAR(1000) DEFAULT NULL | 发布后的 URL |
| error_message | TEXT DEFAULT NULL | |
| published_at | DATETIME DEFAULT NULL | |
| retry_count | INT DEFAULT 0 | |
| created_at | DATETIME | |

索引：`article_batch.user_id`, `article.batch_id`, `publishing_record.article_id`, `publishing_record.platform`

### 1.3 配置扩展 (`app/core/config.py`)

在现有 `Settings` 类中新增以下字段（纯追加，不修改现有行）：

```python
# 视觉模型（图片分析）
vision_model_provider: str = "siliconflow"
vision_model_name: str = "Qwen/Qwen2-VL-72B-Instruct"
vision_model_api_key: str = ""
vision_model_base_url: str = "https://api.siliconflow.cn/v1"

# 文章生成
article_default_count: int = 5
article_min_words: int = 500
article_max_words: int = 800
article_temperature: float = 0.8      # 多样性

# 发布
wechatsync_cli_path: str = "wechatsync"
wechat_mp_appid: str = ""
wechat_mp_appsecret: str = ""
```

同时更新 `cors_origin_list` property，追加新前端端口 `http://localhost:5174`。

### 1.4 图片分析 (`vision.py`)

DeepSeek 没有视觉能力，需要额外的视觉模型做图片→文字转换。

**设计原则**：定义抽象接口，支持多提供商切换。用户后续提供 API key 和模型名称后即可配置使用。

```python
# ===== vision.py — 可插拔的视觉分析接口 =====

from abc import ABC, abstractmethod
from typing import Protocol
from app.core.config import settings

class PhotoDescription(TypedDict):
    object_name: str
    description: str
    suggested_caption: str
    detected_scene: str      # 施工场景 / 产品展示 / 效果对比 / ...

# ---- 抽象接口 ----
class VisionProvider(ABC):
    """视觉模型抽象接口 — 方便后续切换提供商"""

    @abstractmethod
    async def analyze(self, image_base64: str, prompt: str) -> str:
        ...

# ---- OpenAI 兼容提供商 (覆盖大多数) ----
class OpenAICompatibleVisionProvider(VisionProvider):
    """
    支持所有 OpenAI 兼容 API 的视觉模型：
    - SiliconFlow Qwen2-VL (默认)
    - OpenAI GPT-4V / GPT-4o
    - 任何 /v1/chat/completions 兼容端点
    """
    def __init__(self, base_url: str, api_key: str, model: str):
        self.base_url = base_url
        self.api_key = api_key
        self.model = model

    async def analyze(self, image_base64: str, prompt: str) -> str:
        # POST {base_url}/chat/completions
        # messages: [{"role": "user", "content": [
        #     {"type": "text", "text": prompt},
        #     {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_base64}"}}
        # ]}]
        ...

# ---- 工厂函数 ----
def get_vision_provider() -> VisionProvider:
    """根据 config.py 配置返回对应的视觉提供商"""
    return OpenAICompatibleVisionProvider(
        base_url=settings.vision_model_base_url,
        api_key=settings.vision_model_api_key,
        model=settings.vision_model_name,
    )

# ---- 主入口 ----
async def analyze_photos(
    photo_object_names: list[str],
    topic: str,
) -> str:
    """
    1. 从 MinIO 下载每张图片
    2. 逐个调用视觉模型分析（顺序调用，避免内存峰值）
    3. Prompt: "你是一位建筑防潮防水专家。请详细描述这张照片中的施工场景，
       包括：使用了什么材料、施工工艺、现场环境、值得注意的细节。
       输出将用于撰写 GEO 文章，主题为：{topic}"
    4. 汇总所有描述为一段文本
    """
```

**配置（`config.py`）** — 用户后续填入自己的 key 即可：

```python
# 视觉模型（图片分析）— 接口已预留，等你提供 key
vision_model_provider: str = "openai_compatible"   # 提供商类型
vision_model_api_key: str = ""                      # ← 你后面提供
vision_model_name: str = "Qwen/Qwen2-VL-72B-Instruct"  # ← 可换成你的模型
vision_model_base_url: str = "https://api.siliconflow.cn/v1"  # ← 可换成你的端点
```

如果 vision API 未配置（key 为空），自动跳过图片分析，用"用户提供了 X 张现场照片"作为图片占位描述，不影响文章生成流程。

### 1.5 文章生成引擎 (`generator.py`)

三步流水线：

```
输入: topic + photo_descriptions + photo_object_names
                           │
                           ▼
┌──────────────────────────────────────────────────┐
│ Step 1: 检索知识库                                │
│ 对 5 个角度分别构建查询，调用 hybrid_retrieve()    │
│ 每个角度召回 top-8 相关片段                        │
│ 存入 state.retrieved_contexts                     │
└──────────────────────┬───────────────────────────┘
                       ▼
┌──────────────────────────────────────────────────┐
│ Step 2: LLM 规划 5 个差异化角度（一次调用）        │
│ 输入 topic + 知识摘要 + 图片描述                   │
│ 输出 5 组 {angle_key, title_style, tone, query}   │
└──────────────────────┬───────────────────────────┘
                       ▼
┌──────────────────────────────────────────────────┐
│ Step 3: 并行生成 5 篇文章（5 次独立 LLM 调用）     │
│ 每篇 System Prompt 包含：                         │
│  - 角度/风格/语气要求                             │
│  - 该角度对应的知识库检索结果                      │
│  - 图片描述 + 配图位置建议                         │
│  - 字数 500-800                                   │
│  - GEO/SEO 优化要求                               │
│ temperature=0.7~0.8, max_tokens=2048              │
│ 使用 call_llm_with_retry() 容错                   │
│ 顺序调用（避免 LLM 速率限制）+ 指数退避重试       │
└──────────────────────┬───────────────────────────┘
                       ▼
            输出: 5 篇 Markdown 文章
```

**5 个默认角度及对应的知识检索查询**（针对电渗透防潮防水领域定制）：

| Angle Key | 标题风格 | 检索查询关键词 | Temperature |
|-----------|---------|---------------|-------------|
| `technical_detail` | 技术原理解析 | "电渗透防水技术原理 工作原理 技术参数 系统组成" | 0.5 |
| `case_study` | 案例实践分享 | "电渗透防水工程案例 施工案例 地下室防水 应用效果" | 0.7 |
| `benefit_analysis` | 优势效益分析 | "电渗透防水优势 防水效果对比 节能环保 经济效益" | 0.6 |
| `comparison` | 方案对比分析 | "电渗透与传统防水对比 防水方案比较 技术选型" | 0.6 |
| `maintenance_guide` | 选购施工指南 | "电渗透防水维护保养 常见问题 选购注意事项" | 0.5 |

### 1.6 文章生成 LangGraph 管道 (`agents/`)

**State 定义** (`article_state.py`)：

```python
class ArticleBatchState(TypedDict, total=False):
    batch_id: int
    topic: str
    photo_descriptions: str
    photo_object_names: list[str]
    angles: list[dict]                          # 5个角度的元信息
    articles: list[dict]                        # 已生成的文章
    retrieved_contexts: dict[str, list]         # angle_key → 检索结果
    current_angle_index: int
    error: str | None
```

**Graph 结构** (`article_graph.py`)：

```
START → retrieve → generate_batch → evaluate → END
                      ↑                        │
                      └─── (loop × 5) ─────────┘
```

节点说明：
- **retrieve**: 对每个角度构造目标查询，调用 `app/retrieval/fusion.py` 的 `hybrid_retrieve()`，结果存入 `retrieved_contexts`
- **generate_batch**: 循环 5 次，每次读取当前角度 + 对应检索结果，调用 LLM 生成文章，追加到 `articles`，递增 `current_angle_index`，每生成一篇立即写入数据库（用户可实时看到进度）
- **evaluate**: 验证字数、格式，更新批次状态为 `completed` 或 `failed`

### 1.7 发布服务 (`publisher.py`)

**平台分层策略**：

| 平台 | 方式 | 实现细节 |
|------|------|---------|
| **微信公众号** | 官方 API | `POST https://api.weixin.qq.com/cgi-bin/draft/add` 发布到草稿箱；access_token 缓存到 Redis（TTL 7000s） |
| **头条号/百家号/知乎/搜狐号/网易号/CSDN/掘金/简书** | Wechatsync CLI | `asyncio.create_subprocess_exec("wechatsync", "publish", "--path", tmp_md, "--platform", platform)` |
| **不支持自动的平台** | 文件导出 | 返回 DOCX / HTML / MD 供手动上传 |

```python
class Publisher:
    PLATFORMS = {
        "wechat_mp":  {"name": "微信公众号", "method": "direct_api"},
        "toutiao":    {"name": "头条号",     "method": "wechatsync"},
        "baijia":     {"name": "百家号",     "method": "wechatsync"},
        "zhihu":      {"name": "知乎",       "method": "wechatsync"},
        "sohu":       {"name": "搜狐号",     "method": "wechatsync"},
        "wangyi":     {"name": "网易号",     "method": "wechatsync"},
        "csdn":       {"name": "CSDN",       "method": "wechatsync"},
        "juejin":     {"name": "掘金",       "method": "wechatsync"},
        "jianshu":    {"name": "简书",       "method": "wechatsync"},
    }

    async def publish_article(self, article_id: int, platforms: list[str]) -> dict
    async def publish_batch(self, batch_id: int, platforms: list[str]) -> dict
    async def export_article(self, article_id: int, fmt: str) -> bytes  # md/html/docx
    async def export_batch_zip(self, batch_id: int) -> bytes
    async def _publish_via_wechatsync(self, content: str, title: str, platform: str) -> dict
    async def _publish_via_wechat_api(self, article: Article) -> dict
```

### 1.8 API 端点 (`api/articles.py`)

所有路由挂载在 `/api/admin/articles` 下：

```
POST   /batches                        # 创建批次（topic + 可选上传照片）
POST   /batches/{batch_id}/upload-photos  # 上传 3-5 张照片
POST   /batches/{batch_id}/generate    # 启动后台生成任务
GET    /batches/{batch_id}/stream      # SSE 实时进度推送
GET    /batches/{batch_id}             # 批次详情（含所有文章）
GET    /batches                        # 批次列表（分页）
DELETE /batches/{batch_id}             # 删除批次

GET    /articles/{article_id}          # 单篇文章详情
PUT    /articles/{article_id}          # 编辑文章（title/content）
POST   /articles/{article_id}/regenerate # 单独重生成某篇

POST   /articles/{article_id}/publish  # 发布单篇到指定平台
POST   /batches/{batch_id}/publish     # 批量发布整个批次
GET    /articles/{article_id}/publishing-status  # 发布状态查询
GET    /platforms                      # 列出可用平台及当前状态

GET    /articles/{article_id}/export   # 导出单篇 (?format=md|html|docx)
GET    /batches/{batch_id}/export      # 批量导出 ZIP
```

权限：写操作用 `require_permission("write")`，读操作用 `require_auth`。

### 1.9 Pydantic Schemas (`articles/schemas.py`)

```python
class BatchCreate(BaseModel):
    topic: str = Field(min_length=1, max_length=500)

class BatchResponse(BaseModel):
    id: int; topic: str; photo_count: int
    article_count: int; generated_count: int
    status: str; created_at: datetime

class BatchDetailResponse(BatchResponse):
    photo_descriptions: str | None = None
    photo_object_names: list[str] = []
    articles: list["ArticleResponse"] = []
    error_message: str | None = None

class ArticleResponse(BaseModel):
    id: int; batch_id: int; title: str
    word_count: int; angle: str; status: str
    review_status: str
    content: str | None = None         # 详情视图才返回
    image_placement: list | None = None
    publishing_records: list["PublishingRecordResponse"] = []
    created_at: datetime; updated_at: datetime

class ArticleUpdate(BaseModel):
    title: str | None = None
    content: str | None = None

class PublishRequest(BaseModel):
    platform_ids: list[str] = Field(min_length=1)
    article_ids: list[int] | None = None  # None = 发布整个批次

class PublishingRecordResponse(BaseModel):
    id: int; platform: str; platform_name: str
    status: str; published_url: str | None
    error_message: str | None; published_at: datetime | None
```

---

## 二、独立前端应用（article-generator/）

### 2.1 技术栈与初始化

与现有前端一致：Vue 3.5 + TypeScript 5.5 + Vite 5.4 + Element Plus 2.8 + Pinia 2 + Vue Router 4 + Axios

```bash
npm create vite@latest article-generator -- --template vue-ts
cd article-generator
npm install element-plus @element-plus/icons-vue vue-router pinia axios markdown-it
```

### 2.2 目录结构

```
article-generator/                      # 与 enterprise-knowledge-base/ 平级
├── index.html
├── package.json
├── tsconfig.json
├── vite.config.ts                      # port: 5174, proxy /api → :8000
├── Dockerfile
├── src/
│   ├── main.ts
│   ├── App.vue
│   ├── env.d.ts
│   ├── api/
│   │   ├── auth.ts                     # 复用现有项目的登录 API
│   │   ├── articles.ts                # 文章批次 CRUD + 生成 + 发布
│   │   └── platforms.ts               # 发布平台列表
│   ├── stores/
│   │   ├── auth.ts                     # JWT token 管理（镜像现有）
│   │   └── articles.ts                # 文章批次状态
│   ├── router/
│   │   └── index.ts                    # 路由 + auth guard
│   ├── views/
│   │   ├── Login.vue                   # 登录页
│   │   ├── Generator.vue              # ★ 主页面：输入 + 生成 + 预览
│   │   ├── ArticleEdit.vue            # Markdown 编辑器
│   │   ├── BatchHistory.vue           # 历史批次列表
│   │   └── PublishManager.vue         # 发布管理面板
│   └── components/
│       ├── PhotoUploader.vue           # 拖拽上传 + 缩略图预览
│       ├── ArticleCard.vue             # 文章卡片（标题/摘要/操作按钮）
│       ├── ProgressTracker.vue         # 生成进度条（含 SSE 实时更新）
│       ├── PlatformSelector.vue        # 平台多选框
│       ├── MarkdownPreview.vue         # Markdown 渲染预览
│       └── ExportPanel.vue             # 导出控制面板
```

### 2.3 Vite 配置

```typescript
// vite.config.ts
export default defineConfig({
  plugins: [vue()],
  server: {
    port: 5174,
    proxy: {
      "/api": {
        target: "http://localhost:8000",
        changeOrigin: true,
      },
    },
  },
});
```

### 2.4 路由设计

```typescript
const routes = [
  { path: "/login", name: "login", component: () => import("@/views/Login.vue") },
  { path: "/", name: "generator", component: () => import("@/views/Generator.vue"), meta: { requiresAuth: true } },
  { path: "/history", name: "history", component: () => import("@/views/BatchHistory.vue"), meta: { requiresAuth: true } },
  { path: "/article/:id/edit", name: "articleEdit", component: () => import("@/views/ArticleEdit.vue"), meta: { requiresAuth: true } },
  { path: "/batch/:id/publish", name: "publish", component: () => import("@/views/PublishManager.vue"), meta: { requiresAuth: true } },
];
```

### 2.5 页面详细设计

**Generator.vue — 主页面**（单页完成输入→生成→预览全流程）：

```
┌─────────────────────────────────────────────────────────┐
│  📝 批量文章生成器                        [历史记录]    │
│                                                         │
│  ┌─ 第一步：输入主题 ──────────────────────────────┐    │
│  │  文章题目/主题：                                │    │
│  │  ┌─────────────────────────────────────────┐    │    │
│  │  │ 电渗透防潮技术在地下室的应用             │    │    │
│  │  └─────────────────────────────────────────┘    │    │
│  └───────────────────────────────────────────────────┘    │
│                                                         │
│  ┌─ 第二步：上传照片 (3-5张) ─────────────────────┐     │
│  │  ┌──────────────────┐  ┌──────────────────┐     │     │
│  │  │  📷 拖拽或点击   │  │ 工地现场.jpg  ✓  │     │     │
│  │  │  上传照片        │  │ 施工细节.jpg  ✓  │     │     │
│  │  │                  │  │ 效果对比.jpg  ✓  │     │     │
│  │  │  最多5张         │  │ [+ 继续添加]     │     │     │
│  │  └──────────────────┘  └──────────────────┘     │     │
│  └───────────────────────────────────────────────────┘    │
│                                                         │
│  ┌─ 第三步：选择文章角度 (可选，默认全选) ─────────┐    │
│  │  ☑ 技术原理解析   ☑ 案例实践分享                │    │
│  │  ☑ 常见问题解答   ☑ 行业趋势洞察                │    │
│  │  ☑ 选购施工指南                                  │    │
│  └───────────────────────────────────────────────────┘    │
│                                                         │
│  ┌─────────────────────────────────────────────────┐    │
│  │           [🚀 开始生成 5 篇文章]                │    │
│  └─────────────────────────────────────────────────┘    │
│                                                         │
│  ┌─ 生成进度 ─────────────────────────────────────┐    │
│  │  ✅ 图片分析完成                               │    │
│  │  ✅ 知识库检索完成 (匹配 12 条相关知识)         │    │
│  │  ⏳ 正在生成文章...  ████████░░  3/5           │    │
│  │     第4篇: 常见问题解答 — 生成中...            │    │
│  └─────────────────────────────────────────────────┘    │
│                                                         │
│  ┌─ 生成结果 ─────────────────────────────────────┐    │
│  │ ┌──────────────────────────────────────────┐    │    │
│  │ │ #1 电渗透防潮技术原理深度解析             │    │    │
│  │ │ 技术原理 · 658字 · draft   [预览][编辑]  │    │    │
│  │ │ [发布] [导出▾]                           │    │    │
│  │ └──────────────────────────────────────────┘    │    │
│  │ ┌──────────────────────────────────────────┐    │    │
│  │ │ #2 某小区地下室防潮改造纪实               │    │    │
│  │ │ 案例实践 · 712字 · draft   [预览][编辑]  │    │    │
│  │ └──────────────────────────────────────────┘    │    │
│  │ ... (5 篇文章卡片)                            │    │
│  │                                                │    │
│  │  [📤 批量导出 ZIP]   [🚀 一键发布到全平台]     │    │
│  └─────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────┘
```

**ArticleEdit.vue — 文章编辑器**：
- 左侧：Markdown 源码编辑（textarea 或简单的代码编辑器）
- 右侧：实时 Markdown 预览（markdown-it 渲染）
- 可编辑标题和正文
- 显示字数统计
- 保存 → 调用 PUT `/articles/{id}`

**PublishManager.vue — 发布管理**：
- 平台网格（9 个平台，带勾选框）
- "全选/取消全选"
- 每篇文章一行，显示发布状态（pending/success/failed + 链接）
- "发布全部" 按钮
- 底部导出区域：单篇导出 / 批量 ZIP 导出

**BatchHistory.vue — 历史批次**：
- 表格列表（分页）：批次题目、生成时间、文章数、状态
- 点击进入该批次的文章列表
- 支持删除

### 2.6 API 客户端 (`api/articles.ts`)

```typescript
const BASE = "/api/admin/articles";

export async function createBatch(topic: string): Promise<Batch> { ... }
export async function uploadPhotos(batchId: number, files: File[]): Promise<void> { ... }
export async function startGeneration(batchId: number): Promise<void> { ... }
export async function getBatch(batchId: number): Promise<BatchDetail> { ... }
export async function listBatches(page: number, pageSize: number): Promise<PaginatedResponse<Batch>> { ... }
export async function getArticle(articleId: number): Promise<Article> { ... }
export async function updateArticle(articleId: number, data: Partial<Article>): Promise<Article> { ... }
export async function deleteBatch(batchId: number): Promise<void> { ... }
export async function regenerateArticle(articleId: number): Promise<void> { ... }
export async function publishArticles(batchId: number, platformIds: string[], articleIds?: number[]): Promise<void> { ... }
export async function getPublishingStatus(articleId: number): Promise<PublishingRecord[]> { ... }
export async function listPlatforms(): Promise<Platform[]> { ... }
export async function exportArticle(articleId: number, format: string): Promise<Blob> { ... }
export async function exportBatch(batchId: number): Promise<Blob> { ... }

// SSE 连接实时进度
export function subscribeBatchProgress(batchId: number, onProgress: (data) => void): EventSource { ... }
```

### 2.7 认证复用

独立前端完全复用现有后端的 JWT 认证系统。Login.vue 调用 `/api/admin/auth/login`，token 存入 Pinia auth store（镜像 `frontend/src/stores/auth.ts`）。路由器 auth guard 检查 token 有效性。

### 2.8 与现有前端的关系

| 维度 | 现有前端 | 新前端 |
|------|---------|--------|
| 目录 | `enterprise-knowledge-base/frontend/` | `enterprise-knowledge-base/article-generator/` |
| 端口 | 5173 | 5174 |
| 用途 | 知识库管理 + 双智能体聊天 | 批量文章生成 + 发布 |
| 后端 | 同一个 FastAPI :8000 | 同一个 FastAPI :8000 |
| 代码引用 | 无交叉 | 无交叉 |
| 部署 | 独立 Docker 容器 | 独立 Docker 容器（可选 profile） |

**零影响** — 两个前端完全物理隔离，各自独立开发、构建、部署。共享同一个后端 API，但互不依赖。

---

## 三、实施步骤

### 第 1 步：数据库迁移
- 创建 `article_batch`、`article`、`publishing_record` 三张表
- 在 `docker/mysql/init/` 中追加 DDL

### 第 2 步：后端基础设施
- 文件：`config.py`（追加）、`articles/__init__.py`、`articles/models.py`、`articles/schemas.py`、`articles/vision.py`
- vision.py 核心：httpx → SiliconFlow Qwen2-VL → base64 图片 → 结构化中文描述

### 第 3 步：文章生成引擎
- 文件：`articles/generator.py`、`agents/article_state.py`、`agents/nodes/article_retrieve.py`、`agents/nodes/article_generate.py`、`agents/nodes/article_evaluate.py`、`agents/article_graph.py`
- 复用 `app/retrieval/fusion.py` 的 `hybrid_retrieve()`
- 复用 `app/agents/llm.py` 的 `create_llm()` + `call_llm_with_retry()`
- 5 篇文章顺序生成（每次间隔 3 秒防限流），每完成一篇立即写数据库

### 第 4 步：业务服务 + 发布导出
- 文件：`articles/service.py`、`articles/publisher.py`、`api/articles.py`
- service.py：CRUD + `asyncio.create_task` 后台启动生成
- publisher.py：WeChat API（Redis 缓存 token）+ Wechatsync CLI subprocess + DOCX/HTML/MD 导出

### 第 5 步：注册路由
- 在 `app/api/admin/__init__.py` 中新增一行 `include_router(articles_router)`
- 在 `app/api/router.py` 不需要修改（admin 路由已挂载）

### 第 6 步：前端应用
- 初始化 Vue 3 项目 + 安装依赖
- 实现 auth store → Login.vue
- 实现 API client → `api/articles.ts`
- 构建 4 个页面：Generator / ArticleEdit / PublishManager / BatchHistory
- 构建 6 个组件：PhotoUploader / ArticleCard / ProgressTracker / PlatformSelector / MarkdownPreview / ExportPanel
- SSE 实时进度条

### 第 7 步：Docker & 部署
- `article-generator/Dockerfile`（参考现有前端 Dockerfile 模式）
- `docker-compose.yml` 新增可选 service（`profiles: [article-gen]`）
- Nginx 配置新增 upstream + location

---

## 四、内存管理策略（重点）

### 4.1 内存风险分析

文章批量生成涉及以下内存敏感操作：

| 操作 | 内存风险 | 峰值估算 |
|------|---------|---------|
| 图片 base64 编码 | **高** | 5 张 10MB 照片 × 1.33(base64膨胀) = ~66MB |
| 视觉模型 API 调用 | 中 | 每次请求约 2-5MB（HTTP 请求体） |
| 知识库检索 | **高** | 5 个角度 × 8 条 chunk × ~1KB = 40KB（可忽略），但 embedding 模型已驻留内存 ~1.3GB |
| LLM 文章生成 | 中 | 5 次调用 × prompt(~5KB) + response(~2KB) = 可忽略 |
| LangGraph state 累积 | **高** | 若 5 篇文章全部存 state → 5 × 800 字 = ~50KB 文本，但 state 序列化开销大 |
| 前端同时渲染 5 篇文章 | 低 | 5 × ~2KB Markdown ≈ 10KB DOM |

**核心结论**：主要内存风险来自 **图片处理** 和 **LangGraph state 累积**。

### 4.2 内存优化策略

#### 策略 1：逐篇生成、即时持久化（核心策略）

```
❌ 错误做法：5篇文章全部生成完 → 存入 state.articles → 一次性写DB
                     ↓
   5篇文章的完整内容 + LangGraph checkpoint 全部在内存中

✅ 正确做法：生成一篇 → 立即写DB → 从state中清除 → 生成下一篇
                     ↓
   任何时候内存中只有 1 篇文章 + 1 个轻量 state
```

```python
# generator.py 中的实现
async def generate_batch(batch_id: int, state: ArticleBatchState) -> None:
    for i, angle in enumerate(state["angles"]):
        # 1. 生成单篇文章
        article = await generate_single_article(angle, state)
        
        # 2. 立即写入数据库（不累积在 state 中）
        await save_article_to_db(batch_id, article)
        
        # 3. 更新进度计数（轻量整数，不存文章内容）
        await update_batch_progress(batch_id, i + 1)
        
        # 4. 显式释放（Python GC hint）
        del article
        
        # 5. 间隔 3 秒，既防限流也给 GC 喘息时间
        await asyncio.sleep(3)
```

#### 策略 2：图片流式处理，不全部加载

```python
# vision.py — 逐张处理，不累积
async def analyze_photos(photo_object_names: list[str], topic: str) -> str:
    descriptions = []
    for name in photo_object_names:
        # 1. 从 MinIO 流式下载 → 直接 base64
        data = await download_from_minio(name)           # bytes
        img_b64 = base64.b64encode(data).decode()        # 临时
        
        # 2. 调用视觉模型
        desc = await vision_provider.analyze(img_b64, prompt)
        descriptions.append(f"【照片：{name}】{desc}")
        
        # 3. 立即释放 base64 字符串（最占内存的部分）
        del img_b64, data
        
    return "\n\n".join(descriptions)
```

#### 策略 3：前端图片压缩

```typescript
// PhotoUploader.vue — 上传前压缩
async function compressBeforeUpload(file: File): Promise<File> {
  // 目标：max 1920px 宽, JPEG quality 0.8, max 2MB
  const canvas = document.createElement('canvas');
  const ctx = canvas.getContext('2d')!;
  const img = await createImageBitmap(file);
  
  const scale = Math.min(1, 1920 / img.width);
  canvas.width = img.width * scale;
  canvas.height = img.height * scale;
  ctx.drawImage(img, 0, 0, canvas.width, canvas.height);
  
  const blob = await new Promise(r => canvas.toBlob(r, 'image/jpeg', 0.8));
  return new File([blob], file.name, { type: 'image/jpeg' });
}
```

#### 策略 4：检索结果精简

```python
# 不传完整 chunk 文本给 state，传摘要即可
# retrieval 返回 top-8 chunks → 只保留 top-3 给 LLM prompt
# 其余 5 条的元信息用于扩展参考（按需取用）
```

#### 策略 5：LangGraph state 最小化

```python
# article_state.py — state 中只存索引和引用，不存大文本
class ArticleBatchState(TypedDict, total=False):
    batch_id: int
    topic: str                              # ~100B
    photo_descriptions: str                 # ~2KB (压缩后)
    photo_object_names: list[str]           # ~200B
    angles: list[dict]                      # ~1KB (只有元信息)
    retrieved_contexts: dict[str, list]     # ~10KB (只有 top-3)
    current_angle_index: int                # 8B
    error: str | None                       # ~100B
    # ❌ 不存 articles: list[dict] — 每篇生成完立即写DB
```

### 4.3 内存估算（优化后）

| 组件 | 优化后峰值 |
|------|-----------|
| 图片处理（逐张） | ~15MB（单张 base64） |
| LangGraph state | ~15KB |
| 当前生成的文章 | ~3KB |
| embedding 模型（已有） | ~1.3GB（系统常驻，不计入新增） |
| **新增内存总计** | **< 20MB** |

---

## 五、关键技术风险与对策

| 风险 | 对策 |
|------|------|
| DeepSeek 不识别图片 | 视觉 API 抽象接口已预留，支持 OpenAI 兼容的任何多模态模型；key 未配置时自动降级为占位描述 |
| **内存溢出（重点）** | ① 逐篇生成→立即写DB→释放 (见第四节)；② 图片逐张处理不累积；③ 前端上传前压缩；④ state 最小化 |
| 5 篇文章内容雷同 | temperature=0.7~0.8 + 每篇独立的差异化 System Prompt + 不同检索上下文 |
| LLM 速率限制 | 5 篇顺序生成，间隔 3s，`call_llm_with_retry` 指数退避 |
| Wechatsync CLI 环境依赖 | 后端 Dockerfile 预装 `npm install -g @wechatsync/cli`；提供 `/platforms` 端点检查 CLI 可用性 |
| 图片上传过大 | 复用 MinIO 50MB 限制；前端 canvas 压缩到 1920px/2MB 以下 |
| 生成超过 120s 超时 | 使用后台任务（asyncio.create_task）+ SSE 推送进度；Nginx proxy_read_timeout 针对 articles 端点加长 |
| 微信 access_token 过期 | Redis 缓存 TTL=7000s，每次使用前校验 |

---

## 六、验证方案

### 5.1 后端测试
- **单元测试**：`generator.py` 角度规划 / 文章生成 / `publisher.py` 导出函数
- **集成测试**：上传图片 → 视觉分析 → 检索 → 生成 → 保存数据库完整链路
- **API 测试**：所有 15 个端点全覆盖（创建批次 / 上传图片 / 启动生成 / 查询进度 / CRUD / 发布 / 导出）

### 5.2 前端测试
- 组件渲染测试：PhotoUploader / ArticleCard / ProgressTracker
- E2E：从头创建批次 → 上传照片 → 生成 5 篇 → 编辑 1 篇 → 导出 DOCX → 验证文件

### 5.3 端到端验收
1. 启动独立前端 `:5174` + 后端 `:8000`
2. 输入题目"电渗透防潮技术在地下室的应用"
3. 上传 3 张施工照片
4. 点击生成 → 等待 5 篇文章完成 → 验证：
   - 5 篇文章标题不同
   - 每篇字数在 500-800 之间
   - 内容涉及知识库中的专业术语
   - 图片引用（`[IMAGE: ...]` 标记）正确
5. 导出 1 篇为 DOCX → 打开验证格式完整
6. 验证现有系统 `:5173` 功能正常、无回归
7. 性能：5 篇文章生成 < 60 秒

---

## 七、可一键发布的平台汇总

| 平台 | 方式 | GEO 价值 | 备注 |
|------|------|---------|------|
| **微信公众号** | 官方 API | ⭐⭐⭐⭐⭐ | 唯一支持直接 API 发布的 |
| **头条号** | Wechatsync | ⭐⭐⭐⭐⭐ | 流量大，百度收录好 |
| **百家号** | Wechatsync | ⭐⭐⭐⭐⭐ | 百度自家产品，SEO 权重极高 |
| **知乎** | Wechatsync | ⭐⭐⭐⭐ | 长尾搜索流量持续 |
| **CSDN** | Wechatsync | ⭐⭐⭐⭐ | 技术类文章收录快 |
| **掘金** | Wechatsync | ⭐⭐⭐ | 开发者社区 |
| **简书** | Wechatsync | ⭐⭐⭐ | 百度收录好 |
| **搜狐号** | Wechatsync | ⭐⭐⭐ | 新闻源收录 |
| **网易号** | Wechatsync | ⭐⭐⭐ | 新闻源收录 |
| **其他** | 导出 DOCX | ⭐⭐ | 手动上传到不支持自动的平台 |

> Wechatsync 默认发布到**草稿箱**而非直接发布，需在各平台手动确认后正式发布（防止格式问题），这实际上是安全做法。
