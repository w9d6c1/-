# 任务交接文档 — 企业知识库系统 React 管理后台

## 任务描述

**在做的事情**：将 `enterprise-knowledge-base/app/` 下的 React 19 管理后台从纯 localStorage 单机应用改造为对接 FastAPI 后端（`localhost:8000`）的全栈应用。

**当前进度**：主体已完成（100%），所有页面已接入后端，正在做细节优化（最新一项：写作模板系统刚完成，8 个预设 + 自定义均可编辑）。

---

## 必要背景

### 项目结构

```
enterprise-knowledge-base/
├── docker-compose.yml        # 14 个容器（MySQL/PG/Redis/ES/Milvus/MinIO/Nginx...）
├── start.ps1                 # docker compose up -d
├── backend/                  # FastAPI 后端（Python 3.12，端口 8000）
│   └── app/
│       ├── api/articles.py   # 文章/批次/模板/模仿/导出/照片代理 端点
│       ├── articles/         # 文章批量生成模块
│       │   ├── generator.py  # LLM 生成引擎
│       │   ├── imitate.py    # 模仿创作
│       │   ├── vision.py     # 照片视觉分析
│       │   ├── publisher.py  # 发布 + 导出
│       │   ├── service.py    # 业务服务层
│       │   ├── models.py     # ORM 模型
│       │   ├── schemas.py    # Pydantic 模型
│       │   └── template_service.py  # 写作模板 CRUD
│       └── ...
├── app/                      # React 19 管理后台（Vite 7，端口 5175）
│   └── src/
│       ├── api/              # 6 个 API 模块（client/auth/documents/articles/users/dashboard）
│       ├── pages/            # 10 个页面
│       ├── stores/auth.tsx   # AuthProvider + useAuth
│       ├── components/       # AuthGuard / Sidebar / shadcn-ui 组件
│       └── ...
└── article-generator/        # Vue3 文章生成器（另一个前端，不涉及本次改造）
```

### 运行方式

```bash
# 启动后端（Docker）
cd enterprise-knowledge-base
.\start.ps1

# 启动 React 管理后台
cd enterprise-knowledge-base\app
npm run dev -- --host 0.0.0.0
# 访问 http://localhost:5175
```

### 技术栈

- **后端**：FastAPI + SQLAlchemy 2.0 + LangGraph + Milvus + Elasticsearch + DeepSeek LLM + SiliconFlow Vision/Embedding
- **前端**：React 19 + Vite 7 + shadcn/ui + Tailwind CSS 3 + Axios + React Router 7
- **认证**：JWT Bearer Token，后端 `POST /api/admin/auth/login`（用户密码）和 `/phone-login`（手机验证码）
- **数据库**：MySQL（业务数据） + PostgreSQL（LangGraph checkpoint） + Redis（缓存/限流）

### 关键当前配置

- `article_min_words: 1200`，`article_max_words: 3000`（已从 500/800 放宽）
- `max_tokens: 3200`（LLM 生成，已从 1800 提高）
- Vision API Key 已配置但 401 失效，有兜底逻辑
- Vite proxy：`/api` → `http://localhost:8000`

---

## 已完成内容

### 1. React 管理后台全接入后端（100%）

所有页面从 localStorage 改为对接 FastAPI：

| 页面 | 路由 | 状态 |
|------|------|:--:|
| 登录 | `/login` | 手机验证码 + 密码双模式 |
| 仪表盘 | `/` | 独立 try/catch 加载统计/文档/批次 |
| 文章创作 | `/batch-generate` | 5 步向导 + 模仿创作 Tab |
| 文章管理 | `/articles` | 批次列表视图 |
| 文章详情 | `/articles/:id` | 编辑/照片渲染/导出 |
| 知识库 | `/knowledge-base` | 文档上传/分块/向量化/重同步 |
| 模板管理 | `/templates` | 新建/编辑/删除（含预设） |
| 批次任务 | `/schedule` | 批次卡片视图 |
| 发布管理 | `/batch/:id/publish` | 平台选择/批量发布/导出 |
| 用户管理 | `/users` | CRUD |
| 系统设置 | `/settings` | SEO/CMS 本地 + 系统信息 |

### 2. 照片全链路（100%）

- **后端**：`GET /api/admin/articles/photos/{object_name:path}` MinIO 代理
- **前端渲染**：`[IMAGE: 配图建议: xxx]` → `<figure><img/></figure>` 
- **导出嵌入**：DOCX 内联 / HTML base64 / MD 代理链接 / ZIP 含 photos 文件夹
- **兜底**：Vision API 全失败时自动追加 markdown 配图标记指引

### 3. 模仿创作（100%）

- `app/articles/imitate.py`：`analyze_style()` + `imitate_article()` + `retrieve_knowledge()`
- API：`POST /analyze-style`（5 维度分析）+ `POST /imitate`（创建批次 + 生成）
- 前端：批量生成页第二个 Tab，3 步（粘贴 → 分析 → 生成），风格分析卡片展示

### 4. 写作模板（100%）

- ORM：`writing_template` 表（`id, user_id, name, type, prompt_instruction, is_preset, sort_order`）
- 8 个预设（4 结构 + 4 风格），所有模板可编辑删除
- 批量生成流程第 4 步可选模板，可组合结构+风格，也可跳过
- 模板指令拼入 LLM prompt 的 `## 写作模板要求（必须严格遵循）` 章节

---

## 下一步行动

### 立即可做

1. **测试完整流程**：登录 → 创建批次 → 上传照片 → 选角度 → 选模板 → 生成 → 查看照片 → 导出 → 发布
2. **补知识库内容**：在知识库页面上传更多 PDF/Word 文档，提升生成文章的事实质量
3. **修 Vision API Key**：后端 `.env` 里的 `VISION_MODEL_API_KEY` 目前 401 失效，需换成有效的 SiliconFlow key

### 后续建议

1. **文章列表需显示照片预览**：当前批次视图不展示文章的 image_placement 状态
2. **模板可加"重置为默认"按钮**：用户修改了预设模板后能一键恢复
3. **模仿创作可加照片支持**：当前 imitate 接口不支持上传照片到批次，可扩展
4. **文章管理页可改为文章列表视图**：目前是批次视图，某些场景下希望直接看到所有文章
5. **SEO 生成**：当前生成的 [IMAGE] 标记中包含配图建议，但缺少 SEO关键词/标题/描述 的自动生成

### 注意事项

- 后端有 `--reload` 热更新，改 Python 代码无需重启容器
- 前端 Vite HMR 热更新，改代码自动刷新
- SMS 验证码有 60 秒发送间隔限制
- 开发时 `VITE_API_BASE_URL` 设为空走 Vite proxy，生产部署时改为 `https://localhost/api`
