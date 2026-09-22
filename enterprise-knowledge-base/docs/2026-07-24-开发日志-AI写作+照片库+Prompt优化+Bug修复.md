# 2026-07-24 开发日志 — AI 写作模块 + 照片库批量上传 + Prompt 优化 + Bug 修复

## 今日完成

### 阶段一：Vision API 切换

- 从 SiliconFlow `Qwen/Qwen2.5-VL-7B-Instruct`（401 失效）切换到火山引擎豆包 `doubao-seed-2-0-mini-260428`
- 验证：`doubao-seed-2-0-mini` 是全模态模型，支持文本+图片+语音+视频四模态理解
- `.env` 修改：`VISION_MODEL_API_KEY` / `VISION_MODEL_BASE_URL` / `VISION_MODEL_NAME` 三条
- API Key 共用 DeepSeek 的火山引擎账号

### 阶段二：AI 写作模块（全新功能）

| 文件 | 类型 | 说明 |
|------|------|------|
| `backend/app/api/ai_write.py` | **新建** | `POST /api/admin/articles/ai-write/analyze` — LLM 分析用户写作意图，返回推荐模板、字数、照片数、匹配关键词 |
| `backend/app/api/admin/__init__.py` | 修改 | 注册 `ai_write_router`，`prefix="/articles/ai-write"` |
| `app/src/api/aiWrite.ts` | **新建** | `analyzeIntent(description)` → 调用后端分析端点 |
| `app/src/pages/AIWrite.tsx` | **新建** | 4 步流程：描述意图 → AI 推荐配置（模板/字数/照片数）→ 选照片 → 生成展示 |
| `app/src/App.tsx` | 修改 | 加 `Route /ai-write` |
| `app/src/components/layout/Sidebar.tsx` | 修改 | 加「AI 写作」菜单（Wand2 图标） |

### 阶段三：通用 PhotoMatcher 组件

| 文件 | 说明 |
|------|------|
| `app/src/components/PhotoMatcher.tsx` | **新建** — 通用照片匹配选择组件 |
| `app/src/pages/BatchGenerate.tsx` | 修改 — Step 2 配图 Tab 切换（本地上传 / 从照片库选择），接入 PhotoMatcher |
| `app/src/pages/BatchGenerate.tsx` | 修改 — 模仿创作接入 PhotoMatcher，加 `CreateBatch` 按钮后用 PhotoMatcher 选照片 |
| `app/src/api/articles.ts` | 修改 — `imitateArticle` 加 `photo_ids`/`batch_id` 参数；`startGeneration` 加 `usePhotoLibrary`/`minWords`/`maxWords` |
| `backend/app/articles/schemas.py` | 修改 — `ImitateRequest` 加 `photo_ids`/`batch_id` |
| `backend/app/api/articles.py` | 修改 — 模仿端点支持 `photo_ids` 复用已有批次，读照片描述传给 `imitate_article` |
| `backend/app/articles/imitate.py` | 修改 — `imitate_article` 加 `photo_descriptions`/`photo_object_names` 参数，prompt 加照片指令，调用 `_extract_image_placements` 提取配图标记 |

**PhotoMatcher 功能：**
- 智能匹配：调用 `matchPhotos` 取候选池（请求 N+7 张，前端缓存）
- 逐张替换：不满意的点 `↻ 换一个` 从候选池换出
- 手动选择：弹出 Modal 浏览全量照片库 + 标签搜索
- 重新匹配：修改关键词重新调用
- 三种生成方式共用：AI 写作 / 批量生成 / 模仿创作

### 阶段四：照片库批量上传

| 文件 | 说明 |
|------|------|
| `app/src/pages/PhotoLibrary.tsx` | 修改 — 文件输入加 `multiple`，串行逐张上传，最多 20 张，实时进度显示「上传中 (3/20)…」 |

- 后端无需改动（每张调用现有 `POST /photos/upload`，独立的全链路：MinIO 存储 → Vision API 分析 → 入库）
- 串行上传（避免 Vision API 限流），每张失败不影响其他

### 阶段五：SSE + 生成流程 Bug 修复

| 问题 | 文件 | 修复 |
|------|------|------|
| SSE `article_generated` 只发 `{generated: N, total: M}` 计数，前端收不到文章内容 | `backend/app/api/articles.py` | 改为发送完整 `ArticleDetailResponse` 数组（含 `content`） |
| AIWrite 页面生成完成后迟迟不显示完成 | `app/src/pages/AIWrite.tsx` | SSE 只收数据不切换步骤；加独立轮询（每 2 秒 `getBatch` 检查 status）；SSE 没收到的数据轮询自动补捞 |
| 字数滑块设置了但生成不生效 | `generator.py` `service.py` `articles.py` `AIWrite.tsx` `articles.ts` | 5 层穿线：`wordCountMin/Max` → `startGeneration` → `run_generation` → `generate_batch` → `generate_single_article` |
| 批量生成用 PhotoMatcher 选照但不进文章 | `app/src/pages/BatchGenerate.tsx` | 加 `usePhotoLibraryMode` 状态，`handleStartGeneration` 传入 `usePhotoLibrary=true` |
| 模仿创作选照但不进文章 | `imitate.py` + `articles.py` | 后端读取批次关联照片，传入 `imitate_article`，prompt 加照片指令 |
| AIWrite done 步骤照片不渲染 | `app/src/pages/AIWrite.tsx` | 用 `markdownToHtml` 将 `[IMAGE: ...]` 渲染为 `<img>` |

### 阶段六：照片渲染共享工具

| 文件 | 类型 | 说明 |
|------|------|------|
| `app/src/lib/markdown.ts` | **新建** | `markdownToHtml(md, imagePlacement)` — 共享工具函数，解析 `[IMAGE: 配图建议: xxx]` → `<img>` 标签，兼容老 Markdown 格式 |

### 阶段七：Prompt 优化

| 文件 | 说明 |
|------|------|
| `backend/app/articles/generator.py` | `_ARTICLE_PROMPT` 重写 — 6 条硬性约束替换原 SEO/Markdown 格式要求 |
| `backend/app/articles/imitate.py` | `_IMITATE_PROMPT` 重写 — 同样的 6 条硬性约束 |

**6 条约束：**
1. 禁止输出任何 Markdown 符号（#、*、-、>、` 等）
2. 禁止输出思考/推理过程
3. 不分标题、不分点罗列，全文流畅连贯
4. 只输出成品，无前后说明
5. 自然文字衔接，不用符号区分层级
6. 无注释、标记、占位符

**例外：** `[IMAGE: 配图建议: xxx]` 作为配图占位符保留，配合前端 `markdownToHtml` 自动渲染为照片。

---

## 今日新增/修改文件清单

### 新建文件（5 个）

```
backend/app/api/ai_write.py         — AI 写作意图分析端点
app/src/api/aiWrite.ts              — 前端 AI 写作 API 层
app/src/components/PhotoMatcher.tsx — 通用照片匹配选择组件
app/src/pages/AIWrite.tsx           — AI 写作页面
app/src/lib/markdown.ts             — Markdown + 照片渲染工具函数
```

### 修改文件（13 个）

```
backend/.env                                     — Vision API 切换到豆包
backend/app/api/admin/__init__.py                — 注册 ai_write 路由
backend/app/api/articles.py                      — SSE 发完整 ArticleDetailResponse；模仿端点支持照片；start_generation 加字数参数
backend/app/articles/schemas.py                  — ImitateRequest 加 photo_ids/batch_id
backend/app/articles/imitate.py                  — imitate_article 支持照片；Prompt 加 6 条约束
backend/app/articles/generator.py                — _ARTICLE_PROMPT 重写；加 min/max_words 参数穿越；加 top_p 准备（DEFAULT_ANGLES）
backend/app/articles/service.py                  — run_generation 加 min/max_words 参数
app/src/App.tsx                                  — 加 /ai-write 路由
app/src/components/layout/Sidebar.tsx             — 加「AI 写作」菜单
app/src/pages/BatchGenerate.tsx                   — Step 2 Tab 切换接入 PhotoMatcher；模仿创作接入 PhotoMatcher；usePhotoLibraryMode
app/src/pages/PhotoLibrary.tsx                    — 批量上传（multiple + 串行 + 进度）
app/src/pages/AIWrite.tsx                         — 4 步流程 + SSE 轮询兜底 + 照片渲染
app/src/api/articles.ts                           — startGeneration 加 usePhotoLibrary/minWords/maxWords；imitateArticle 加 photo_ids/batch_id
```

---

## 当前系统状态

| 组件 | 状态 |
|------|------|
| 后端 FastAPI | 端口 8000，健康运行 |
| 前端 Vite | 端口 5175，健康运行 |
| 文章生成 LLM | DeepSeek deepseek-chat（`sk-b99a...`） |
| Vision API | 豆包 doubao-seed-2-0-mini（火山引擎） |
| kb-nginx | 一直重启（`react-app:5175` 服务不存在，不影响使用） |

---

## 注意事项

- 后端容器重启后需等约 40 秒模型加载完成
- 前端端口 5175，不是 Docker 内的 5173
- Vision API Key 和 LLM Key 是两个不同的 Key（豆包 vs DeepSeek），在 `.env` 中分别配置
- 文章生成后 `[IMAGE: 配图建议: xxx]` 标记是靠 `_extract_image_placements` 提取 → `image_placement` 存 DB → `markdownToHtml` 渲染
- PhotoMatcher 的 `matchPhotos` 请求 count+7 张用于候选池，`replacePhoto` 从池中换出
- AI 写作的 `handlePhotosConfirmed` 不走 SSE 切换步骤，改用独立轮询，避免 React 竞态
