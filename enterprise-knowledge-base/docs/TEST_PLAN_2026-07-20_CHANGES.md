# 2026-07-20 改动全量回归 — 测试计划

> **版本:** v1.0  
> **日期:** 2026-07-21  
> **基于:** `docs/ops/2026-07-20-开发调试日志.md` 14 文件改动  
> **目标:** 验证性能调优、输出格式优化、流式端点修复、测试修复的正确性与稳定性

---

## 目录

1. [测试环境与前置条件](#1-测试环境与前置条件)
2. [测试用例总览](#2-测试用例总览)
3. [专项一：Milvus 检索性能调优](#3-专项一milvus-检索性能调优)
4. [专项二：输出格式优化与 Prompt 重写](#4-专项二输出格式优化与-prompt-重写)
5. [专项三：流式端点修复](#5-专项三流式端点修复)
6. [专项四：安全/回归修复验证](#6-专项四安全回归修复验证)
7. [专项五：并发与降级压测](#7-专项五并发与降级压测)
8. [测试执行计划](#8-测试执行计划)
9. [通过标准与准出条件](#9-通过标准与准出条件)

---

## 1. 测试环境与前置条件

### 1.1 环境要求

| 组件 | 要求 |
|------|------|
| Docker Compose | 11 服务正常运行（不含监控栈 prometheus/grafana/loki/promtail） |
| Python 3.12 | `uvicorn` 可 reload |
| MySQL 8.0 | 业务数据库含种子数据 |
| PostgreSQL 16 | LangGraph checkpoint 数据库可连接 |
| Redis 7 | 缓存服务可连接 |
| Milvus 2.4 | standalone 模式，`coll_public` / `coll_internal` / `coll_customer` 已创建 |
| Elasticsearch 8.15 | `idx_bm25_public` / `idx_bm25_internal` / `idx_bm25_customer` 已创建 |
| DeepSeek API | API Key 有效且配额充足 |

### 1.2 测试数据准备

- [ ] `coll_internal` 含 ≥ 5 条向量数据（验证 load 不超时）
- [ ] `coll_customer` 含 ≥ 5 条向量数据
- [ ] ES 三个 Index 各含 ≥ 5 条文档（BM25 检索可用）
- [ ] FAQ 条目 ≥ 20 条（customer ≥ 10, internal ≥ 5, public ≥ 5）
- [ ] 敏感词配置 ≥ 10 条（含 `str` 类型规则，验证类型归一化修复）
- [ ] 测试用户 ≥ 3 个（`superadmin` / `dept_admin` / `readonly`）

### 1.3 前置检查

```
□ docker compose ps → 11 服务全部 healthy
□ curl https://localhost/api/health → 200
□ curl https://localhost/api/agent/info → modules 全部 ok
□ Milvus coll_internal load 成功（≤ 10s）
□ Milvus coll_customer load 成功（≤ 10s）
□ ES 三个 Index 健康 (status != red)
```

---

## 2. 测试用例总览

| 专项 | 用例数 | 优先级 | 预估耗时 | 改动文件 |
|------|--------|--------|----------|----------|
| 专项一：Milvus 检索性能调优 | 18 | 🔴 CRITICAL | 25min | `retrieval/milvus_client.py`, `agents/customer/retrieve.py`, `agents/nodes/retrieve.py`, `agents/nodes/tools.py` |
| 专项二：输出格式优化与 Prompt 重写 | 22 | 🔴 CRITICAL | 30min | `agents/customer/generate.py`, `agents/nodes/generate.py`, `agents/customer/faq.py`, `agents/nodes/faq.py`, `agents/nodes/output.py` |
| 专项三：流式端点修复 | 16 | 🔴 CRITICAL | 25min | `app/api/agent/__init__.py` |
| 专项四：安全/回归修复验证 | 20 | 🟡 HIGH | 20min | `agents/nodes/output.py`, `api/admin/auth.py`, `docker/waf/waf-proxy.conf`, `docker/nginx/conf.d/default.conf` |
| 专项五：并发与降级压测 | 10 | 🟡 HIGH | 20min | 全部改动文件 |
| **合计** | **86** | | **~120min** | 14 文件 |

---

## 3. 专项一：Milvus 检索性能调优

### 背景

- `retrieval/milvus_client.py` — 模块级连接去重、`coll.load(timeout=10)`、`dense_search` 异常捕获、`loop.run_in_executor` 线程池
- `agents/customer/retrieve.py` — scope 循环 `asyncio.wait_for(timeout=15)`
- `agents/nodes/retrieve.py` — scope 循环 `asyncio.wait_for(timeout=15)`
- `agents/nodes/tools.py` — 工具调用检索 `asyncio.wait_for(timeout=15)`

### TC-MILVUS-001: Collection Load 超时保护

| 项目 | 内容 |
|------|------|
| **前置条件** | Milvus 正常运行，`coll_customer` 为空 collection（无数据） |
| **测试步骤** | 1. 清空 `coll_customer` 的实体数据<br>2. 调用 `dense_search` 或 `hybrid_retrieve` 查询 customer scope<br>3. 监控事件循环是否被阻塞 |
| **测试数据** | 空 `coll_customer` collection |
| **通过标准** | `coll.load(timeout=10)` 在 10s 内超时返回，不阻塞 asyncio 事件循环；其他 scope 请求不受影响 |

### TC-MILVUS-002: Collection Load 正常加载

| 项目 | 内容 |
|------|------|
| **前置条件** | `coll_internal` 含 ≥ 386 条实体 |
| **测试步骤** | 1. 重启 backend 容器<br>2. 发送内部智能体查询请求<br>3. 记录 `coll.load()` 耗时 |
| **测试数据** | 任意内部知识库提问 |
| **通过标准** | load 在 ≤ 10s 内完成；密集检索返回非空结果（非降级为仅 BM25） |

### TC-MILVUS-003: Dense Search 异常捕获

| 项目 | 内容 |
|------|------|
| **前置条件** | Milvus 连接可用，collection 未加载 |
| **测试步骤** | 1. 释放 collection（`coll.release()`）<br>2. 调用 `dense_search`<br>3. 验证是否抛出可控异常或返回空结果 |
| **测试数据** | 任意查询文本 |
| **通过标准** | 不抛出未捕获异常，不阻塞事件循环；返回空结果或明确错误信息，检索自动降级为仅 BM25 |

### TC-MILVUS-004: 连接去重

| 项目 | 内容 |
|------|------|
| **前置条件** | 多个并发请求 |
| **测试步骤** | 1. 同时发起 5 个内部智能体请求<br>2. 验证 `connections.connect` 只被调用一次<br>3. 检查日志中无重复连接警告 |
| **测试数据** | 5 条不同查询 |
| **通过标准** | `_ensure_connected()` 只执行一次实际连接；无 `Connection already exists` 错误日志 |

### TC-MILVUS-005: Thread Pool 执行隔离

| 项目 | 内容 |
|------|------|
| **前置条件** | `_get_or_create_collection_async` 使用 `loop.run_in_executor` |
| **测试步骤** | 1. 在 collection 创建期间同时处理其他 HTTP 请求<br>2. 验证 `/api/health` 仍然返回 200 |
| **测试数据** | 并发 10 个请求，其中 1 个触发 collection 创建 |
| **通过标准** | 健康检查请求不被阻塞，所有并发请求在 2s 内得到响应 |

---

### TC-MILVUS-006: 客服检索超时 (asyncio.wait_for)

| 项目 | 内容 |
|------|------|
| **前置条件** | `agents/customer/retrieve.py` 加入 `asyncio.wait_for(timeout=15)` |
| **测试步骤** | 1. Mock Milvus 的 load 方法延迟 20s<br>2. 调用客服智能体检索入口 |
| **测试数据** | 任意客服咨询 |
| **通过标准** | 15s 后抛出 `asyncio.TimeoutError`，由上层 catch 处理，返回降级响应 |

### TC-MILVUS-007: 正常检索不误触发超时

| 项目 | 内容 |
|------|------|
| **前置条件** | Milvus 正常运行，数据已加载 |
| **测试步骤** | 1. 发送 10 条客服查询请求<br>2. 记录每条请求的检索耗时 |
| **测试数据** | "特莱顿电渗透防水技术如何运作"/"施工流程"等真实 FAQ |
| **通过标准** | 所有请求在 15s 内正常返回，无 TimeoutError |

### TC-MILVUS-008: 内部检索超时

| 项目 | 内容 |
|------|------|
| **前置条件** | `agents/nodes/retrieve.py` 加入 `asyncio.wait_for(timeout=15)` |
| **测试步骤** | 1. 模拟 Milvus 连接中断（禁用 MinIO）<br>2. 调用内部智能体检索 |
| **通过标准** | 15s 超时后降级为仅 BM25 检索，返回结果或友好错误提示 |

### TC-MILVUS-009: 工具调用检索超时

| 项目 | 内容 |
|------|------|
| **前置条件** | `agents/nodes/tools.py` 的 `search_knowledge_base` 工具加入 `asyncio.wait_for` |
| **测试步骤** | 1. 正常环境触发工具调用（如查询多个 scope）<br>2. 模拟某个 scope 响应超时 |
| **通过标准** | 超时 scope 返回空结果，其他 scope 正常返回；LLM 能基于部分结果生成回答 |

---

### TC-MILVUS-010 ~ 018: 参数化边界测试

| 用例 | 条件 | 预期 |
|------|------|------|
| TC-MILVUS-010 | `timeout=0.1` | 立即 TimeoutError，降级 |
| TC-MILVUS-011 | `timeout=None` | 无超时，等待至自然完成 |
| TC-MILVUS-012 | scope 列表为空 | 不执行检索，直接返回 |
| TC-MILVUS-013 | 3 个 scope 全部加载失败 | 全部降级 BM25，3 次 WARNING 日志 |
| TC-MILVUS-014 | 1/3 scope 加载失败 | 失败 scope 跳过，其余正常 |
| TC-MILVUS-015 | 空 collection + load timeout | load 超时，dense search 返回空 |
| TC-MILVUS-016 | coll.load() 10s 临界值 | 刚好 10s 加载完成可通过 |
| TC-MILVUS-017 | 并发 20 请求同时检索 | 无事件循环死锁 |
| TC-MILVUS-018 | `connections.has_connection` 重建 | 删除连接后自动重建 |

---

## 4. 专项二：输出格式优化与 Prompt 重写

### 背景

- `agents/customer/generate.py` — 客服 Prompt 10 条规则
- `agents/nodes/generate.py` — 内部 Prompt 8 条规则
- `agents/customer/faq.py` / `agents/nodes/faq.py` — `[FAQ 精准匹配]` 改为 `参考FAQ答案：`
- `agents/nodes/output.py` — 3 层正则兜底清理
- `agents/nodes/tools.py` — `tool_decision_node` content 置空、`_format_docs_for_llm` 去标签

### TC-GEN-001: 客服 Prompt 企业身份

| 项目 | 内容 |
|------|------|
| **前置条件** | 客服智能体生成链路可调用 |
| **测试步骤** | 1. 提问 "你们公司叫什么"<br>2. 检查回答中是否出现企业全称 |
| **测试数据** | 简单身份询问 |
| **通过标准** | 回答包含 "特莱顿电渗透防水技术有限公司" |

### TC-GEN-002: 禁止 Markdown 标题

| 项目 | 内容 |
|------|------|
| **前置条件** | 生成链路可调用 |
| **测试步骤** | 1. 提问需列举多项的问题（如 "施工流程有哪些步骤"）<br>2. 检查回答中是否出现 `#` `##` `###` |
| **测试数据** | "特莱顿的施工流程分哪几个阶段" |
| **通过标准** | 回答中 **不含** `# ## ###` 等 Markdown 标题符号 |

### TC-GEN-003: 禁止 Markdown 分隔线/列表

| 项目 | 内容 |
|------|------|
| **前置条件** | 生成链路可调用 |
| **测试步骤** | 1. 提问需列举对比的问题<br>2. 检查回答中是否出现 `---` `-` `*` 列表标记 |
| **测试数据** | "对比特莱顿和其他防水的优劣" |
| **通过标准** | 回答中 **不含** `---` 分隔线，**不含** `-` `*` 开头列表（仅允许自然段落 + `**加粗**`） |

### TC-GEN-004: 允许加粗

| 项目 | 内容 |
|------|------|
| **前置条件** | 生成链路可调用 |
| **测试步骤** | 1. 提问需要强调关键词的问题<br>2. 检查回答中是否出现 `**关键字**` 格式 |
| **测试数据** | 任意问题 |
| **通过标准** | 回答中可含 `**...**` 加粗格式 |

### TC-GEN-005: 禁止思考过程泄露

| 项目 | 内容 |
|------|------|
| **前置条件** | 生成链路可调用 |
| **测试步骤** | 1. 提问需要多步检索的问题<br>2. 检查回答中是否出现 "让我先查一下"、"首先"、"根据搜索结果" 等思考短语 |
| **测试数据** | 复杂技术问题 |
| **通过标准** | 回答 **不含** 思考过程文本，直接给出答案 |

### TC-GEN-006: 禁止机器标签

| 项目 | 内容 |
|------|------|
| **前置条件** | 生成链路可调用，FAQ 有匹配项 |
| **测试步骤** | 1. 提问命中 FAQ 的问题<br>2. 检查输出中是否出现 `[来源:xxx]` `[FAQ 精准匹配]` `[文档1]` 等标签 |
| **测试数据** | FAQ 精准匹配提问 |
| **通过标准** | 回答中 **不含** 任何 `[来源:...]`、`[FAQ ...]`、`[文档N]` 标签 |

### TC-GEN-007: 客服字数控制

| 项目 | 内容 |
|------|------|
| **前置条件** | 客服智能体 |
| **测试步骤** | 1. 发送 10 条客服问题<br>2. 统计每条回答字数 |
| **测试数据** | 10 条不同客服咨询 |
| **通过标准** | 简单问题 ≤ 150 字，复杂问题 ≤ 400 字（80% 符合即可） |

### TC-GEN-008: 内部智能体字数控制

| 项目 | 内容 |
|------|------|
| **前置条件** | 内部智能体 |
| **测试步骤** | 1. 发送 5 条内部问题<br>2. 统计每条回答字数 |
| **通过标准** | 简单问题 ≤ 200 字，详细问题 ≤ 500 字 |

### TC-GEN-009: FAQ Context 标签清洗

| 项目 | 内容 |
|------|------|
| **前置条件** | FAQ 节点 context 字段改为 `参考FAQ答案：\n{答案}` |
| **测试步骤** | 1. 在 FAQ 节点输出日志中检查 context 字段内容<br>2. 验证无 `[FAQ 精准匹配]` |
| **通过标准** | context 以 `参考FAQ答案：` 开头，不含旧标签 `[FAQ 精准匹配]` |

---

### TC-OUTPUT-001: 机器标签正则兜底

| 项目 | 内容 |
|------|------|
| **前置条件** | `validate_output_node` 第 1 层正则 |
| **测试步骤** | 1. 构造包含 `[来源:xxx]` `[FAQ 精准匹配]` `[文档1]` 的字符串<br>2. 经 `validate_output_node` 处理<br>3. 验证清理结果 |
| **测试数据** | "根据[来源:技术文档]和[FAQ 精准匹配]，答案是XXX。[文档1]也有说明。" |
| **通过标准** | 输出为 "根据和，答案是XXX。也有说明。"（所有机器标签移除） |

### TC-OUTPUT-002: Markdown 符号正则兜底

| 项目 | 内容 |
|------|------|
| **前置条件** | `validate_output_node` 第 2 层正则 |
| **测试步骤** | 1. 构造包含 `# 标题` `## 小标题` `---` `- 列表` `* 项目` 的字符串<br>2. 经正则清理 |
| **测试数据** | "# 施工流程\n---\n- 第一步\n- 第二步\n* 注意事项" |
| **通过标准** | 输出不含任何 Markdown 标记符号 |

### TC-OUTPUT-003: 思考文本正则兜底

| 项目 | 内容 |
|------|------|
| **前置条件** | `validate_output_node` 第 3 层正则 |
| **测试步骤** | 1. 构造含 "首先我来查询相关资料" "用户问的是" "根据搜索结果" 的句子<br>2. 经正则清理 |
| **测试数据** | "首先我来查询相关的技术资料。根据搜索结果，特莱顿的电渗透技术就是这样。" |
| **通过标准** | 输出仅保留 "特莱顿的电渗透技术就是这样。" |

### TC-OUTPUT-004: 三层防线全量回归

| 项目 | 内容 |
|------|------|
| **前置条件** | 同时包含三类污染 |
| **测试步骤** | 1. 构造含机器标签 + Markdown + 思考文本的混合字符串<br>2. 经 `validate_output_node` 处理 |
| **测试数据** | `[FAQ 精准匹配]\n# 答案\n首先我先查一下，根据资料显示，**特莱顿**很好。\n---\n[来源:doc1]` |
| **通过标准** | 输出仅 "**特莱顿**很好。"，无任何污染残留 |

### TC-OUTPUT-005: 正常文本不误伤

| 项目 | 内容 |
|------|------|
| **前置条件** | 正常回答不包含污染 |
| **测试步骤** | 1. 传入正常纯文本回答（含 `**加粗**`、数字 `1. 2.`、自然段落）<br>2. 经 `validate_output_node` 处理 |
| **测试数据** | "特莱顿电渗透防水技术的**核心优势**包括：\n1. 环保无污染\n2. 施工简单" |
| **通过标准** | 输出不变，`**加粗**` 和数字编号保留 |

---

### TC-GEN-010 ~ 022: 参数化 Prompt 规则验证

| 用例 | Prompt 规则 | 输入 | 预期 |
|------|-------------|------|------|
| TC-GEN-010 | 禁止 `` ` `` 代码块 | "告诉我 API 怎么调用" | 不含 Markdown 代码块 |
| TC-GEN-011 | 禁止 `>` 引用 | "这篇文章怎么看" | 不含 `>` 引用格式 |
| TC-GEN-012 | 正常换行保留 | 多段落长回答 | 保留自然 `\n` 换行 |
| TC-GEN-013 | 空输入 | `question=""` | 优雅处理，返回提示 |
| TC-GEN-014 | 超长输入 | 5000 字问题 | 不崩溃，正确截断或处理 |
| TC-GEN-015 | 含特殊字符 | `<script>alert(1)</script>` | HTML 标签被 LLM 忽略，无 XSS 输出 |
| TC-GEN-016 | emoji 输入 | "你好 🎉 请问" | 正常处理，不崩溃 |
| TC-GEN-017 | 纯数字输入 | "12345" | 返回合理回复 |
| TC-GEN-018 | FAQ context 编码 | context 含 `\n` `\t` 转义 | 正确传递，不转义破坏 |
| TC-GEN-019 | tool_decision content 为空 | 函数调用场景 | AI message content 为 `""`，不含思考文本见 TC-TOOL-001 |
| TC-GEN-020 | `_format_docs_for_llm` 去标签 | 含 `[文档1] 来源:xxx` | 格式化为 `文档1: content` |
| TC-GEN-021 | `search_knowledge_base` 返回 | 工具返回结果 | 不含 `[来源:xxx]` |
| TC-GEN-022 | 内部 + 客服 Prompt 隔离 | 同一问题分别用两个 agent | 客服 Prompt 10 条 ≠ 内部 Prompt 8 条，各自执行 |

---

## 5. 专项三：流式端点修复

### 背景

- `app/api/agent/__init__.py`
  - 内部流式 `_stream_events`：新增 `done` 事件
  - 客服流式 `_customer_stream_events`：`on_chain_end` 过滤空 `final_answer`
  - 两个端点 `done` 答案执行 7 条正则清洗

### TC-STREAM-001: 内部流式 Done 事件

| 项目 | 内容 |
|------|------|
| **前置条件** | SSE 流式连接可建立 |
| **测试步骤** | 1. 发送内部智能体流式请求<br>2. 收集所有 SSE 事件<br>3. 检查最后一个事件 |
| **测试数据** | `POST /api/agent/internal/chat/stream` |
| **通过标准** | 最后收到 `event: done`，包含 `{"data": {"answer": "..."}}`，answer 已清洗 |

### TC-STREAM-002: 客服流式 Done 事件

| 项目 | 内容 |
|------|------|
| **前置条件** | SSE 流式连接可建立 |
| **测试步骤** | 1. 发送客服智能体流式请求<br>2. 收集所有 SSE 事件 |
| **测试数据** | `POST /api/agent/customer/chat/stream` |
| **通过标准** | 收到 `event: done`，无重复 done（每个节点结束不发送 done） |

### TC-STREAM-003: Done 事件不重复发送

| 项目 | 内容 |
|------|------|
| **前置条件** | 客服智能体图含 5+ 节点 |
| **测试步骤** | 1. 发送流式请求<br>2. 统计 `event: done` 出现次数 |
| **通过标准** | 整个流式响应中 `done` 事件恰好出现 **1 次** |

### TC-STREAM-004: 空 Final Answer 不触发 Done

| 项目 | 内容 |
|------|------|
| **前置条件** | 图执行中某节点 `final_answer=""` |
| **测试步骤** | 1. 构造空答案场景<br>2. 检查流式事件 |
| **通过标准** | 空 `final_answer` 不触发 `done` 事件 |

### TC-STREAM-005: Done 答案 7 条正则清洗

| 项目 | 内容 |
|------|------|
| **前置条件** | 后端返回可能含污染的答案 |
| **测试步骤** | 1. 模拟 LLM 返回含 `[FAQ 精准匹配]`、`# 标题`、思考文本的答案<br>2. 检查 done 事件中的 `answer` 字段 |
| **通过标准** | done 事件中的答案已完成 7 条正则清洗，无污染 |

### TC-STREAM-006: Token 流式传输不中断

| 项目 | 内容 |
|------|------|
| **前置条件** | LLM 流式生成正常 |
| **测试步骤** | 1. 发送流式请求<br>2. 验证 `data: ` 事件连续发送 |
| **通过标准** | 首 token 延迟 ≤ 1.5s，中间无断流 |

### TC-STREAM-007: 流式 + 非流式一致性

| 项目 | 内容 |
|------|------|
| **前置条件** | 同一问题 |
| **测试步骤** | 1. 分别调用流式和非流式端点<br>2. 比较 done 事件 answer 和非流式响应的 answer |
| **通过标准** | 两者语义一致（清洗后内容相同） |

### TC-STREAM-008: 客户端断连处理

| 项目 | 内容 |
|------|------|
| **前置条件** | 流式进行中 |
| **测试步骤** | 1. 建立 SSE 连接<br>2. 在收到第 3 个 token 后断开连接<br>3. 检查后端日志 |
| **通过标准** | 后端不崩溃，无未捕获异常；图执行正确取消 |

---

### TC-STREAM-009 ~ 016: 端点边界测试

| 用例 | 测试点 | 预期 |
|------|--------|------|
| TC-STREAM-009 | 并发 5 路流式 | 各自独立，不串线 |
| TC-STREAM-010 | Accept: text/event-stream 缺失 | 返回 406 或优雅拒绝 |
| TC-STREAM-011 | 超大输入（100KB body） | 返回 413 或截断 |
| TC-STREAM-012 | 空 message | 返回错误提示 |
| TC-STREAM-013 | Scope 切换流式 | scope=internal → scope=customer 各自正确 |
| TC-STREAM-014 | 流式清洗含 unicode | 中文、emoji 不被正则破坏 |
| TC-STREAM-015 | Connection: close 中断 | 后端资源正确释放 |
| TC-STREAM-016 | 流式结束后心跳 | 无额外事件发送 |

---

## 6. 专项四：安全/回归修复验证

### 背景

- `agents/nodes/output.py` — `filter_sensitive_words` 类型归一化（str → dict）
- `api/admin/auth.py` — 新增 `POST /login` 端点
- `tests/security/test_isolation_probe.py` — 500 条跨库探针
- `tests/security/test_memory_batch.py` — 10 组多轮对话
- `docker/waf/waf-proxy.conf` — auth + agent 路由 `modsecurity off`
- `docker/nginx/conf.d/default.conf` — Grafana location 注释

### TC-SEC-001: 敏感词 str 类型兼容

| 项目 | 内容 |
|------|------|
| **前置条件** | `_SENSITIVE_RULES` 列表含 `str` 类型元素 |
| **测试步骤** | 1. 配置 `["禁止词1", {"pattern": "正则词", "replacement": "***"}]`<br>2. 调用 `filter_sensitive_words("包含禁止词1和正则词")` |
| **测试数据** | 混合类型规则列表 |
| **通过标准** | str 元素自动包装为 `{"pattern": ..., "replacement": "***"}`；`AttributeError` 不再抛出 |

### TC-SEC-002: 敏感词 dict 类型不变

| 项目 | 内容 |
|------|------|
| **前置条件** | `_SENSITIVE_RULES` 含标准 dict 元素 |
| **测试步骤** | 1. 仅配置 dict 类型规则<br>2. 验证过滤行为 |
| **通过标准** | 行为和修复前完全一致 |

### TC-SEC-003: Login 端点正常返回

| 项目 | 内容 |
|------|------|
| **前置条件** | 数据库有用户 |
| **测试步骤** | 1. `POST /api/admin/auth/login` with `Form(username=, password=)`<br>2. 验证响应 |
| **通过标准** | 200 + `{"token": "...", "user": {...}}` |

### TC-SEC-004: Login 错误凭证

| 项目 | 内容 |
|------|------|
| **前置条件** | 数据库有用户 |
| **测试步骤** | 1. `POST /api/admin/auth/login` 错误密码 |
| **通过标准** | 401 + `{"detail": "用户名或密码错误"}` |

### TC-SEC-005: Login 缺失字段

| 项目 | 内容 |
|------|------|
| **前置条件** | 用户名或密码为空 |
| **测试步骤** | `POST /api/admin/auth/login` 缺 username |
| **通过标准** | 422 (Unprocessable Entity) |

---

### TC-ISO-001: 500 条跨库探针 — 检索隔离

| 项目 | 内容 |
|------|------|
| **前置条件** | `TestBatch500IsolationProbes` 类 |
| **测试步骤** | 1. 运行 `pytest tests/security/test_isolation_probe.py -v`<br>2. 100 条内部知识术语 × 7 种问句模板 + MD5 变体 = 500 条唯一查询 |
| **通过标准** | 500 条客服查询 **全部不触发** internal scope；泄漏率 = **0%** |

### TC-ISO-002: 500 条跨库探针 — FAQ 隔离

| 项目 | 内容 |
|------|------|
| **前置条件** | 同上 |
| **测试步骤** | 验证 500 条 FAQ 查询全部不命中 internal scope |
| **通过标准** | 命中率 = 0 |

### TC-ISO-003: 500 条跨库探针 — 输出无泄漏

| 项目 | 内容 |
|------|------|
| **前置条件** | 同上 |
| **测试步骤** | 100 条图输出验证无内部术语泄露 |
| **通过标准** | 无内部术语、文件名、employee 名称泄露 |

### TC-ISO-004: 500 条跨库探针 — 路由无 internal 路径

| 项目 | 内容 |
|------|------|
| **前置条件** | 同上 |
| **测试步骤** | 验证 500 条路由决策 |
| **通过标准** | 无一条被路由到 internal 处理路径 |

---

### TC-MEM-001: 10 组多轮对话 — 上下文连贯

| 项目 | 内容 |
|------|------|
| **前置条件** | `tests/security/test_memory_batch.py` 10 种指代类型 |
| **测试步骤** | 运行 `pytest tests/security/test_memory_batch.py::TestMemoryCoherence -v` |
| **通过标准** | 近指代/远指代/角色/序数/缩略/单指代/链式/数值/对比/跨主题 全部正确解析 |

### TC-MEM-002: Thread 隔离

| 项目 | 内容 |
|------|------|
| **前置条件** | 两个独立 thread_id |
| **测试步骤** | 1. Thread A 和 B 交错对话<br>2. 验证各自上下文独立 |
| **通过标准** | Thread B 不访问 Thread A 的历史消息 |

### TC-MEM-003: Checkpoint 持久化

| 项目 | 内容 |
|------|------|
| **前置条件** | PostgreSQL checkpoint 数据库可用 |
| **测试步骤** | 1. 进行 3 轮对话<br>2. 重启 Backend<br>3. 继续第 4 轮对话 |
| **通过标准** | 第 4 轮能正确引用前 3 轮上下文 |

### TC-MEM-004: Token 截断

| 项目 | 内容 |
|------|------|
| **前置条件** | 对话历史超过模型上下文窗口 |
| **测试步骤** | 1. 进行 20+ 轮超长对话<br>2. 验证 trim_history 行为 |
| **通过标准** | 早期轮次被截断，但最近 N 轮保留；不因 token 超限而报错 |

---

### TC-INFRA-001: WAF ModSecurity 豁免

| 项目 | 内容 |
|------|------|
| **前置条件** | `docker/waf/waf-proxy.conf` 中 `/api/admin/auth/` 和 `/api/agent/` 设 `modsecurity off` |
| **测试步骤** | 1. `POST /api/admin/auth/login` 带 JSON body<br>2. 检查是否返回 400 |
| **通过标准** | 不返回 400（ModSecurity 规则不会误拦）；正常处理 JSON body |

### TC-INFRA-002: Nginx Grafana 注释

| 项目 | 内容 |
|------|------|
| **前置条件** | Grafana 容器已停止，nginx 配置中 Grafana location 已注释 |
| **测试步骤** | 1. 启动 nginx<br>2. 检查 nginx 是否正常启动 |
| **通过标准** | nginx 启动成功，无 `host not found in upstream "grafana"` 错误 |

### TC-INFRA-003: WAF 重启后 Nginx DNS 刷新

| 项目 | 内容 |
|------|------|
| **前置条件** | WAF 重启获得新 IP |
| **测试步骤** | 1. 重启 WAF 容器<br>2. 重启 Nginx 容器<br>3. 发送请求至后端 |
| **通过标准** | 不返回 502；Nginx 正确解析 WAF 新 IP |

---

## 7. 专项五：并发与降级压测

### TC-STRESS-001: 混合并发请求

| 项目 | 内容 |
|------|------|
| **前置条件** | 全链路正常 |
| **测试步骤** | 同时发起：5 客服 FAQ + 3 内部检索 + 2 流式 + 2 登录 |
| **测试数据** | 12 并发混合请求 |
| **通过标准** | 无请求超时（30s），无 5xx 错误，健康检查持续 200 |

### TC-STRESS-002: Milvus 全部不可用降级

| 项目 | 内容 |
|------|------|
| **前置条件** | Milvus 容器停止 |
| **测试步骤** | 1. `docker stop kb-milvus`<br>2. 发送内部检索请求 |
| **通过标准** | 自动降级为仅 BM25；返回结果（可能有损，但不断路） |

### TC-STRESS-003: ES 不可用降级

| 项目 | 内容 |
|------|------|
| **前置条件** | ES 容器停止 |
| **测试步骤** | 发送检索请求 |
| **通过标准** | 仅 Milvus 向量检索可用，返回结果 |

### TC-STRESS-004: DeepSeek API 超时降级

| 项目 | 内容 |
|------|------|
| **前置条件** | Mock DeepSeek API 超时 |
| **测试步骤** | 1. 模拟 API 超时<br>2. 发送生成请求 |
| **通过标准** | 返回友好错误提示"AI 服务暂不可用，请稍后重试"；不泄露 raw error |

### TC-STRESS-005: 长时间运行内存稳定性

| 项目 | 内容 |
|------|------|
| **前置条件** | Backend 正常运行 |
| **测试步骤** | 1. 持续发送请求 10 分钟（每 5s 一条）<br>2. 监控内存变化 |
| **通过标准** | 内存无持续增长（无泄漏）；GC 正常回收 |

### TC-STRESS-006: FAQ 500 条并发匹配

| 项目 | 内容 |
|------|------|
| **前置条件** | FAQ 向量库含 500+ 条 |
| **测试步骤** | 1. 并发 50 条 FAQ 匹配请求<br>2. 记录 p95/p99 延迟 |
| **通过标准** | p95 ≤ 500ms（缓存命中）；缓存未命中 ≤ 2s |

### TC-STRESS-007: FAQ match + LLM 润色全链路

| 项目 | 内容 |
|------|------|
| **前置条件** | 客服生成链路完整 |
| **测试步骤** | 10 条 FAQ 命中 + LLM 润色请求 |
| **通过标准** | p95 ≤ 3s |

### TC-STRESS-008: 跨 Scope 检索精度

| 项目 | 内容 |
|------|------|
| **前置条件** | 三个 scope 均有数据 |
| **测试步骤** | 查询 "公司制度"（应为 internal）vs "产品价格"（应为 customer） |
| **通过标准** | scope 路由正确，同一查询仅检索对应 scope |

### TC-STRESS-009: 流式并发 10 路

| 项目 | 内容 |
|------|------|
| **前置条件** | SSE 端点正常 |
| **测试步骤** | 同时建立 10 路 SSE 连接 |
| **通过标准** | 全部正常结束，done 事件正确发送；无连接泄漏 |

### TC-STRESS-010: 重启恢复验证

| 项目 | 内容 |
|------|------|
| **前置条件** | 进行中流式连接 |
| **测试步骤** | 1. 建立 SSE 连接<br>2. 重启 backend<br>3. 重新连接后继续对话 |
| **通过标准** | Checkpoint 恢复后能继续对话；新连接正常 |

---

## 8. 测试执行计划

### 执行顺序

| 阶段 | 内容 | 用例 | 耗时 | 依赖 |
|------|------|------|------|------|
| **Phase 1** | 前置检查 | — | 5min | Docker 全部 healthy |
| **Phase 2** | 专项四（回归修复） | TC-SEC-001~005, TC-ISO-001~004, TC-MEM-001~004, TC-INFRA-001~003 | 20min | Phase 1 |
| **Phase 3** | 专项一（Milvus 性能） | TC-MILVUS-001~018 | 25min | Phase 1 |
| **Phase 4** | 专项二（输出格式） | TC-OUTPUT-001~005, TC-GEN-001~022 | 30min | Phase 1 |
| **Phase 5** | 专项三（流式端点） | TC-STREAM-001~016 | 25min | Phase 1 |
| **Phase 6** | 专项五（并发压测） | TC-STRESS-001~010 | 20min | Phase 2~5 |
| **Phase 7** | 全量回归 | `pytest tests/ -v` | 5min | Phase 2~6 |

### 自动化执行命令

```bash
# Phase 2: 安全/回归修复
pytest tests/unit/test_safety_words.py tests/security/test_isolation_probe.py tests/security/test_memory_batch.py -v

# Phase 3: Milvus + 检索
pytest tests/unit/test_milvus_client.py tests/unit/test_es_client.py tests/unit/test_fusion.py -v

# Phase 4: 生成 + 输出
pytest tests/unit/test_day4_nodes2.py tests/unit/test_faq_node.py -v

# Phase 5: 流式端点 (需手动验证 SSE 事件)
pytest tests/unit/test_llm.py -v
# 手动: curl -N https://localhost/api/agent/internal/chat/stream

# Phase 6: 并发压测
pytest tests/performance/test_bench.py -v

# Phase 7: 全量回归
pytest tests/ --cov=app --cov-report=term-missing -v
```

---

## 9. 通过标准与准出条件

### 红线（任一项失败 → 🔴 BLOCKED）

| 编号 | 指标 | 阈值 |
|------|------|------|
| R1 | `coll.load(timeout=10)` 不阻塞事件循环 | 0 次阻塞 |
| R2 | `filter_sensitive_words` str 类型兼容 | 0 次 AttributeError |
| R3 | `POST /login` 端点可用 | 200 响应 |
| R4 | 500 条跨库探针泄漏率 | = 0% |
| R5 | 流式 `done` 事件送达 | 100% 请求收到 |
| R6 | 输出无 `[来源:xxx]` `[FAQ 精准匹配]` 标签 | 0 次出现 |

### 量化指标

| 指标 | 目标 | 当前基准 |
|------|------|----------|
| 客服 FAQ 命中延迟 | ≤ 300ms | ~300ms ✅ |
| 客服 FAQ + LLM | ≤ 3s | ~2.2s ✅ |
| 流式首 token | ≤ 1.5s | ~880ms-1.4s ✅ |
| Milvus load 成功率 | = 100% | coll_internal 不稳定 ⚠️ |
| 检索超时降级 | 100% 触发降级 | — |
| 测试覆盖率 | ≥ 80% | 32% ⚠️ |
| 测试通过率 | ≥ 95% | 91.1% ⚠️ |

### 准出决策

| 结果 | 判定 |
|------|------|
| 全部红线 ✅ + 量化指标达成 | 🟢 **准出** |
| 红线全部 ✅ + 量化指标部分未达成 | 🟡 **有条件准出**（记录遗留问题） |
| 任一条红线 ❌ | 🔴 **BLOCKED**（修复后重新验证） |
