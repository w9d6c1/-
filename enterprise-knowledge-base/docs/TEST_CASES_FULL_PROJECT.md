# 全项目测试用例（自动化）— 标准用例表 + 执行计划 + 通过标准

> **版本:** v1.0
> **日期:** 2026-08-17
> **范围:** 覆盖 Backend (FastAPI) / Vue3 前端 / React 管理后台 / 发布桥接器
> **形式:** 标准 QA 用例表 + 自动化测试映射 + 执行计划 + 准出条件

---

## 1. 测试环境与前置条件

| 组件 | 要求 |
|------|------|
| Python 3.12 + pytest 8.x | `backend/` 内运行，使用内存 SQLite + ASGI Transport，**无需外部服务** |
| Node 24 + npm | 前端 / React 后台 / 发布桥接器依赖安装完毕 |
| Docker (可选) | 仅 e2e 验证真实链路或人工回归时使用 |
| Chrome / Edge | e2e 测试浏览器（本地未下载 Playwright Chromium 时用 `playwright.chrome.config.ts` 走系统 Chrome） |

依赖安装：

```bash
# backend
cd enterprise-knowledge-base/backend && pip install -r requirements.txt pytest pytest-cov pytest-asyncio

# frontend
cd enterprise-knowledge-base/frontend && npm install

# react admin app
cd enterprise-knowledge-base/app && npm install

# publisher-bridge
cd enterprise-knowledge-base/publisher-bridge && npm install
```

---

## 2. 测试用例总览

| 模块 | 自动化用例数 | 优先级 | 说明 |
|------|--------------|--------|------|
| Backend — 智能体对话 / SSE 流式 | 5（新增） | 🔴 CRITICAL | 流式 token/done/error、done 单次、降级 |
| Backend — 企业微信回调 | 7（新增） | 🟡 HIGH | URL 验签、消息接收、异常 403/503 |
| Backend — 速率限制 | 3（新增） | 🟡 HIGH | 智能体限流、debug 旁路策略 |
| Backend — 既有套件 | ~160 | 🔴 CRITICAL | unit/integration/e2e/security/perf |
| Vue3 前端 — 单元 | 27（新增） | 🟡 HIGH | auth store / chat store / agent API |
| Vue3 前端 — E2E | 9（新增） | 🟡 HIGH | 登录、内部问答、FAQ 管理 |
| React 管理后台 | 36（新增） | 🟡 HIGH | 登录/路由守卫/API 拦截器/仪表盘/工具 |
| 发布桥接器 | 18（新增） | 🟡 HIGH | markdown 转换、健康检查、发布队列 |
| **合计（新增）** | **105** | — | — |

---

## 3. 各模块标准用例表

### 3.1 智能体对话与 SSE 流式（Backend）

> 自动化: `backend/tests/integration/test_agent_stream_api.py`

| 用例ID | 模块 | 优先级 | 前置条件 | 操作步骤 | 预期结果 |
|--------|------|--------|----------|----------|----------|
| TC-STREAM-001 | 内部智能体 | 🔴 | 无外部服务 | POST `/api/agent/internal/chat/stream`，Graph 依次产生 token/token/done | 响应为 `text/event-stream`；事件序列 `token→token→done`；done 含完整 answer；结尾 `data: [DONE]` |
| TC-STREAM-002 | 内部智能体 | 🔴 | 同上 | 多个 on_chain_end 事件 | `done` 事件**恰好出现 1 次** |
| TC-STREAM-003 | 内部智能体 | 🔴 | Graph 抛异常 | 发起流式请求 | 收到 `type:error` 事件，message=`系统内部错误`；服务不崩溃 |
| TC-STREAM-004 | 内部智能体 | 🔴 | 空事件流 | 发起流式请求 | 兜底 `done`，answer 含 `未找到相关信息` |
| TC-STREAM-005 | 客服智能体 | 🔴 | 客服 Graph | POST `/api/agent/customer/chat/stream` | 事件 `token→done`，answer 正确 |
| TC-STREAM-006 | 客服智能体 | 🔴 | 客服 Graph 异常 | 发起流式请求 | `type:error` 事件送达 |

### 3.2 企业微信回调（Backend）

> 自动化: `backend/tests/integration/test_wecom_callback_api.py`

| 用例ID | 模块 | 优先级 | 前置条件 | 操作步骤 | 预期结果 |
|--------|------|--------|----------|----------|----------|
| TC-WECOM-001 | 回调验证 | 🟡 | wecom 未配置 | GET `/api/channels/wecom/callback` | 503 |
| TC-WECOM-002 | 回调验证 | 🟡 | 配置 token/aes/corp_id | 构造合法签名 GET 验证 | 200，返回解密后的 echostr |
| TC-WECOM-003 | 回调验证 | 🟡 | 同上 | 传入错误签名 | 403 |
| TC-WECOM-004 | 消息接收 | 🟡 | wecom 未配置 | POST callback | 503 |
| TC-WECOM-005 | 消息接收 | 🟡 | 配置完成 | 加密消息 XML + 正确签名 POST | 200 空串；`handle_message` 被调度 1 次 |
| TC-WECOM-006 | 消息接收 | 🟡 | 配置完成 | 错误签名 POST | 403 |
| TC-WECOM-007 | 消息接收 | 🟡 | 配置完成 | 非法 XML body POST | 403（环境 rich 日志器已打桩隔离） |

### 3.3 速率限制（Backend）

> 自动化: `backend/tests/security/test_rate_limit.py`

| 用例ID | 模块 | 优先级 | 前置条件 | 操作步骤 | 预期结果 |
|--------|------|--------|----------|----------|----------|
| TC-RATE-001 | 内部智能体 | 🟡 | reset 限流器 | 连续 30 次 chat 后第 31 次 | 前 30 次 200，第 31 次 **429** |
| TC-RATE-002 | 客服/内部隔离 | 🟡 | 同上 | 触达内部 30/min 限流后调客服 | 客服仍 200（60/min 独立计数） |
| TC-RATE-003 | 管理登录 | 🟡 | `settings.debug` 可切换 | 验证 `_rate_limit` 装饰行为 | debug=True 直接返回原函数；debug=False 包裹限流 |

### 3.4 知识库文档 / FAQ / 词典 / 采集 / 文章 / 文案（Backend 既有套件）

> 自动化: `backend/tests/unit/`、`backend/tests/integration/`（~160 用例，覆盖）
> 代表性用例映射：

| 用例ID | 模块 | 自动化位置 |
|--------|------|-----------|
| TC-DOC-001~004 | 文档上传/分块/清理/删除级联 | `tests/unit/test_document*.py`、`tests/integration/test_document_sync.py` |
| TC-FAQ-001~005 | FAQ CRUD/版本/审核/向量重载 | `tests/unit/test_faq_*.py`、`tests/integration/test_faq_chain.py` |
| TC-DICT-001~004 | 同义词/敏感词/禁词/反馈/未答复 | `tests/unit/test_dictionary.py`、`test_feedback.py`、`test_unanswered.py` |
| TC-COLLECT-001~010 | 采集适配器/去重/清洗/图片 | `tests/unit/test_collector_*.py`、`test_image_extractor.py` |
| TC-ART-001~020 | 文章批次/生成/照片/发布/模板 | `tests/unit/test_article_*.py`、`tests/integration/test_articles_api.py` |
| TC-CPY-001~008 | 文案/脚本/热门话题 | `tests/unit/test_copywriting.py` |
| TC-AUTH-001~010 | 注册/登录/权限/部门隔离 | `tests/unit/test_auth*.py`、`test_scope_permission.py`、`test_dept_isolation.py` |
| TC-ISO-001~004 | 500 条跨库隔离探针 | `tests/security/test_isolation_probe.py` |
| TC-MEM-001~004 | 多轮记忆/线程隔离/Checkpoint | `tests/security/test_memory_batch.py`、`tests/unit/test_checkpoint.py` |
| TC-FALL-001~012 | 异常降级（LLM/Milvus/ES/Redis/MinIO/PG） | `tests/unit/test_emergency_*.py`、`test_emergency_degradation.py` |
| TC-LOG-001~004 | 审计/反馈/安全日志 | `tests/unit/test_audit_log.py`、`test_monitoring_*.py` |
| TC-PIPE-001~004 | 全链路文档→问答 | `tests/e2e/test_full_pipeline.py` |

### 3.5 Vue3 前端单元（新增）

> 自动化: `frontend/src/stores/__tests__/auth.test.ts`、`chat.test.ts`、`frontend/src/api/__tests__/agent.test.ts`

| 用例ID | 模块 | 优先级 | 前置条件 | 操作步骤 | 预期结果 |
|--------|------|--------|----------|----------|----------|
| TC-FE-AUTH-01~08 | auth store | 🟡 | Pinia + mock API | 登录/登出/持久化/init 恢复/失效登出/角色解析 | token 与 user 状态一致；坏 token 自动登出；JWT 角色/部门正确解析 |
| TC-FE-CHAT-01~12 | chat store | 🟡 | Pinia + mock 流 | 发送消息/流式 token/done/error/未答复上报/点赞/线程切换/历史 | 消息最终化、置信度写入、低置信自动上报、线程水合正确 |
| TC-FE-API-01~07 | agent API | 🟡 | mock fetch | 客服/内部 chat、Bearer 注入、401 跳转、SSE 解析 | 请求头正确；401 清 token 跳登录；token/done/[DONE] 解析正确；坏行跳过 |

### 3.6 Vue3 前端 E2E（新增）

> 自动化: `frontend/tests/e2e/login-flow.spec.ts`、`chat-internal.spec.ts`、`admin-faq.spec.ts`

| 用例ID | 模块 | 优先级 | 前置条件 | 操作步骤 | 预期结果 |
|--------|------|--------|----------|----------|----------|
| TC-E2E-LOGIN-01 | 登录页 | 🟡 | mock 验证码/登录接口 | 输入手机号→获取验证码 | 展示 `验证码: 123456` |
| TC-E2E-LOGIN-02 | 登录页 | 🟡 | 同上 | 空手机号点获取验证码 | 提示 `请输入手机号` |
| TC-E2E-LOGIN-03 | 登录页 | 🟡 | 同上 | 输入手机号+验证码→登录 | 跳转 `#/admin` |
| TC-E2E-LOGIN-04 | 登录页 | 🟡 | mock 401 | 错误验证码登录 | 展示后端错误消息 |
| TC-E2E-CHAT-01 | 内部问答 | 🟡 | token + mock SSE | 发送问题，流返回 error 事件 | 展示友好错误文案 |
| TC-E2E-CHAT-02 | 内部问答 | 🟡 | token + mock SSE | 低置信度 done | 展示转人工答复 |
| TC-E2E-FAQ-01~03 | FAQ 管理 | 🟡 | token + mock 数据 | 列表加载/状态标签/表单校验/行操作按钮 | 列表与标签正确；未填全禁用新增按钮 |

### 3.7 React 管理后台（新增，原零测试）

> 自动化: `app/src/**/*.test.{ts,tsx}`（vitest + Testing Library）

| 用例ID | 模块 | 优先级 | 自动化位置 |
|--------|------|--------|-----------|
| TC-APP-UTIL-01~05 | `cn()` 合并工具 | 🟡 | `src/lib/utils.test.ts` |
| TC-APP-MD-01~11 | markdown→HTML 渲染/配图 | 🟡 | `src/lib/markdown.test.ts` |
| TC-APP-API-01~04 | axios 拦截器（token 注入/401 跳转） | 🔴 | `src/api/client.test.ts` |
| TC-APP-AUTH-01~05 | AuthProvider 登录/登出/持久化/坏数据 | 🔴 | `src/stores/auth.test.tsx` |
| TC-APP-GUARD-01~02 | AuthGuard 未登录跳转 | 🔴 | `src/components/AuthGuard.test.tsx` |
| TC-APP-LOGIN-01~04 | 登录页（验证码/密码登录/错误） | 🔴 | `src/pages/Login.test.tsx` |
| TC-APP-DASH-01~04 | 仪表盘数据渲染/告警/接口失败兜底 | 🟡 | `src/pages/Dashboard.test.tsx` |

### 3.8 发布桥接器（新增，原零测试）

> 自动化: `publisher-bridge/tests/markdown-to-html.test.mjs`、`publish-api.test.mjs`

| 用例ID | 模块 | 优先级 | 操作步骤 | 预期结果 |
|--------|------|--------|----------|----------|
| TC-BRIDGE-MD-01~11 | Markdown→HTML | 🟡 | 各类 markdown 片段 | 代码块/标题/列表/图片/链接/加粗/引用/hr/段落正确转换 |
| TC-BRIDGE-API-01 | 健康检查 | 🟡 | GET `/health` | 200，service/group_ports 正确 |
| TC-BRIDGE-API-02 | 参数校验 | 🟡 | 缺参数 POST `/api/publish` | 400 `缺少必要参数` |
| TC-BRIDGE-API-03 | 未知组 | 🟡 | 非法 group | 400 `未知账号组` |
| TC-BRIDGE-API-04 | 扩展未连接 | 🟡 | 无 WS 客户端 | 200 `success:false`，`Chrome 扩展未连接` |
| TC-BRIDGE-API-05 | 发布成功 | 🟡 | mock 扩展返回 postUrl | 200 `success:true` + url |
| TC-BRIDGE-API-06 | 扩展失败 | 🟡 | mock 扩展返回 error | 200 `success:false` + 错误文案 |
| TC-BRIDGE-API-07 | 队列串行 | 🟡 | 同组 3 并发发布 | 任意时刻 in-flight ≤ 1；全部成功；队列清空 |
| TC-BRIDGE-API-08 | CORS | 🟡 | OPTIONS 预检 | 204 + `Access-Control-Allow-Origin: *` |

---

## 4. 测试执行计划

| 阶段 | 命令 | 位置 |
|------|------|------|
| Backend 全量 | `pytest tests/ --cov=app --cov-report=term-missing` | `backend/` |
| Backend 新增长尾 | `pytest tests/integration/test_agent_stream_api.py tests/integration/test_wecom_callback_api.py tests/security/test_rate_limit.py -p no:rich` | `backend/` |
| Vue3 前端单元 | `npm test` | `frontend/` |
| Vue3 前端 E2E | `npx playwright test --config=playwright.chrome.config.ts`（系统 Chrome） | `frontend/` |
| React 后台单元 | `npm test` | `app/` |
| React 后台类型/构建 | `npm run build` | `app/` |
| 发布桥接器 | `npm test` | `publisher-bridge/` |

> 注：Windows 下 e2e 使用 `playwright.chrome.config.ts`（走系统 Chrome，免下载 Chromium）；CI/有网络环境可直接 `npx playwright test`。

---

## 5. 通过标准与准出条件

### 5.1 自动化闸门（全部通过 → 可交付）

| 编号 | 闸门 | 命令 | 目标 |
|------|------|------|------|
| G1 | Backend 测试 | `pytest tests/` | 全绿；覆盖率 ≥ 80% |
| G2 | Vue3 前端单元 | `npm test` | 全绿 |
| G3 | Vue3 前端 E2E | `npx playwright test` | 全绿 |
| G4 | React 后台单元 + 构建 | `npm test && npm run build` | 全绿 + 类型通过 |
| G5 | 发布桥接器 | `npm test` | 全绿 |

### 5.2 已知环境注意点（非用例缺陷）

1. **Backend bcrypt**：本机 bcrypt 新版本对 >72 字节密码抛错，`tests/unit/test_auth.py` 中 3 例失败为**既有环境漂移**，与本次新增用例无关。
2. **rich 日志器**：格式含 `ExpatError` 的 traceback 会触发 rich 渲染崩溃；`test_malformed_xml_returns_403` 已通过打桩隔离，e2e 建议加 `-p no:rich`。
3. **debug 模式**：`settings.debug=True` 时管理端登录等 `_rate_limit` 旁路（设计如此），用例已按此行为断言。

### 5.3 准出决策

```
G1~G5 全部通过        →  🟢 准出
仅 G3（E2E）环境原因失败 →  🟡 有条件准出（记录截图/报告）
任一条新用例失败       →  🔴 修复后重跑
```

---

> **编制:** AI Agent · **审核:** （待指定）· **版本:** v1.0 · 2026-08-17
