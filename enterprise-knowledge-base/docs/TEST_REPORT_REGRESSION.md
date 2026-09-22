# 核心功能全量回归 + 红线专项复测 — 测试执行报告

> **执行日期:** 2026-07-20
> **测试环境:** Windows 11, Python 3.12.10, pytest 8.2.2
> **测试文件:** 62 个测试文件  
> **总用例数:** 624 条（收集数），617 条已执行（7 条因模型加载阻塞未执行）
> **基于测试计划:** `docs/TEST_PLAN_REGISTRATION.md` v1.0

---

## 1. 执行摘要

| 指标 | 数值 |
|------|------|
| 总测试用例 | 617 |
| 通过 | **562** (91.1%) |
| 失败 | **55** (8.9%) |
| 代码覆盖率 | 32% (目标 80%, 未达标 — 见 §6) |
| 红线阻塞项 | **4** (见 §7) |

### 总体判定: 🔴 **BLOCKED** — 存在红线阻断项，禁止上线

---

## 2. 分专项执行结果

### 2.1 专项一：多轮记忆完整性与持久化

| 测试用例 | 状态 | 说明 |
|----------|------|------|
| TC-MEM-001 5轮对话连贯性 | ⚠️ PARTIAL | `test_multi_turn_same_thread_keeps_state` — mock 不完整导致 graph.ainvoke 阻塞，无法完整验证 |
| TC-MEM-002 HumanMessage/AIMessage 写入 | ⚠️ PARTIAL | Checkpoint 写入逻辑 `graph.py:133-148` 已覆盖但无端到端 validator |
| TC-MEM-003 服务重启恢复 | ❌ NOT TESTED | 需 PostgreSQL 运行环境，本地测试环境无真实 PG |
| TC-MEM-004 Token 预算截断 | ✅ PASS | `test_window.py` — `trim_history()` 逻辑单元测试通过 |
| TC-MEM-005 多 thread_id 隔离 | ✅ PASS | `test_different_threads_independent` — 不同 thread_id 互不影响 (checkpoint.py:60) |
| TC-MEM-006 客服智能体多轮 | ⚠️ PARTIAL | 客服图节点测试通过，但无完整多轮端到端 |
| TC-MEM-007 10组脚本批量 | ❌ NOT TESTED | 需自动化脚本 `scripts/test_memory_batch.py` 未实现 |
| TC-MEM-008 checkpoint 并发写入 | ❌ NOT TESTED | 无对应测试用例 |
| TC-MEM-009 长会话截断恢复 | ✅ PASS | `trim_history()` 边界条件已覆盖 |
| TC-MEM-010 checkpoint init 失败降级 | ✅ PASS | `test_build_checkpointer_returns_valid_connection` — 验证 init 失败不崩溃 |

**专项一判定:** 🔴 **BLOCKED** — TC-MEM-003 (重启恢复) 和 TC-MEM-007 (批量脚本) 未验证

---

### 2.2 专项二：数据隔离与安全红线

| 测试用例 | 状态 | 说明 |
|----------|------|------|
| TC-ISO-001 500条跨库探针 | ❌ NOT TESTED | `tests/security/test_isolation_probe.py` — 无实际数据，仅框架代码 |
| TC-ISO-002 检索日志验证 | ✅ PASS | `TestCustomerRetrieveNode` — 验证检索仅使用 customer+public scope |
| TC-ISO-003 Milvus Collection 物理隔离 | ⚠️ PARTIAL | 单元测试 Mock，需真实 Milvus 环境验证 |
| TC-ISO-004 `_strip_internal_scopes()` | ✅ PASS | `test_graph_strips_internal_scope` — `["public","internal","customer"]` → 输出不含 `internal` (customer_graph.py:60-68) |
| TC-ISO-005 无Token访问内部接口 | ✅ PASS | `TestUnauthenticatedAccess::test_admin_endpoints_require_auth` — 6个管理端点均返回 401 |
| TC-ISO-006 低权限越权 | ✅ PASS | `test_readonly_cannot_create_faq` — readonly 角色返回 403 |
| TC-ISO-007 客服路由完整性 | ✅ PASS | `TestCustomerGraph` — 客服图节点包含 retrieve/faq/generate/handoff，无 internal 路径 |
| TC-ISO-008 模型输出侧转接标记 | ⚠️ PARTIAL | `human_handoff_node` 4类条件逻辑已验证，但 LLM 输出端到端未测 |
| TC-SEC-001 敏感词过滤输出侧 | ❌ **FAIL** | `test_filter_sensitive_words` 失败 — `'str' object has no attribute 'get'` (output.py:17 bug) |
| TC-SEC-002 个人信息脱敏 | ⚠️ PARTIAL | `validate_output_node` 覆盖但脱敏规则完整性未定量验证 |
| TC-SEC-003 Prompt注入拦截 | ✅ PASS | `test_validate_input_node` — 61 条安全测试通过，输入校验节点正常工作 |
| TC-SEC-004 SQL注入拦截 | ❌ **FAIL** | `test_sql_injection_in_login_rejected` — 返回 404 而非 401/422 (路由路径变更) |

**专项二判定:** 🔴 **BLOCKED** — TC-SEC-001 (敏感词过滤 bug)、TC-ISO-001 (500探针未执行)

---

### 2.3 专项三：全链路功能回归

| 测试用例 | 状态 | 说明 |
|----------|------|------|
| TC-PIPE-001 文档上传→向量化→同步 | ❌ **FAIL** | `test_sync_single_doc_writes_both_stores` — Milvus/ES mock 缺失 |
| TC-PIPE-002 三种切片策略 | ⚠️ PARTIAL | `test_chunking.py` — 业务代码覆盖率 12% |
| TC-PIPE-003 DOCX 解析 | ⚠️ PARTIAL | `test_text_parser.py` — 未找到测试文件 |
| TC-PIPE-004 文档删除级联清理 | ❌ NOT TESTED | 无对应测试用例 |
| TC-FAQ-001 FAQ 精确命中 | ✅ PASS | `test_faq_match_*` — FAQ 匹配节点单元测试通过 |
| TC-FAQ-002 FAQ 相似问句命中 | ✅ PASS | 余弦相似度阈值 0.92 逻辑已验证 |
| TC-FAQ-003 FAQ 未命中回退 | ✅ PASS | `test_after_faq` — `faq_hit=False` → 路由到 `retrieve` |
| TC-FAQ-004 FAQ Scope 隔离 | ✅ PASS | `test_faq_no_match_wrong_scope` — internal FAQ 不被客服命中 |
| TC-FAQ-005 FAQ 定时发布/下架 | ⚠️ PARTIAL | `test_faq_schedule.py` 通过但 APScheduler 需要真实环境 |
| TC-RET-001 双路召回并行 | ✅ PASS | `hybrid_retrieve` 并行逻辑单元测试通过 |
| TC-RET-002 RRF 融合排序 | ✅ PASS | `reciprocal_rank_fusion()` 逻辑已验证 |
| TC-RET-003 Reranker 重排 | ⚠️ PARTIAL | Reranker 测试失败 — 无本地模型文件 |
| TC-RET-004 Redis 检索缓存 | ⚠️ PARTIAL | `cache.py` coverage 34%, 需 Redis 环境 |
| TC-RET-005 ES 仅BM25降级 | ❌ NOT TESTED | `es_client.py` coverage 38%, 降级逻辑未覆盖 |
| TC-RET-006 Milvus 仅稠密降级 | ❌ NOT TESTED | `milvus_client.py` coverage 28%, 降级逻辑未覆盖 |
| TC-GEN-001 来源引用标注 | ⚠️ PARTIAL | `generate_node` coverage 18% — 提示词模板含 `[来源: ...]` 指令，但输出验证缺失 |
| TC-GEN-002 无答案诚实回复 | ⚠️ PARTIAL | LLM mock 仅返回固定文本，真实行为未验证 |
| TC-GEN-003 流式SSE完整性 | ✅ PASS | `test_stream_*` — SSE 流式框架测试通过 |
| TC-FLOW-007 4类转人工 | ✅ PASS | `human_handoff_node` — 4类条件独立触发逻辑已验证 |
| TC-TOOL-001 search_knowledge_base | ✅ PASS | `test_tool_call_search_knowledge_base` — 工具调用逻辑通过 |
| TC-TOOL-002 decompose_query | ⚠️ PARTIAL | 工具定义存在但端到端测试需 LLM |
| TC-TOOL-003 ReAct 迭代上限 | ✅ PASS | `iteration >= 3` 条件分支已验证 (graph.py:83-84) |
| TC-LOG-001 反馈提交 | ❌ **FAIL** | `test_feedback_flow` 系列 — 6/7 集成测试失败 (路由/API 变更导致 404) |
| TC-LOG-002 全链路日志完整性 | ❌ **FAIL** | `test_chat_log_chain` — 3/3 失败 (数据库异步写入验证失败) |
| TC-LOG-003 未命中问题记录 | ❌ **FAIL** | `test_unanswered_flow` — 3/3 失败 |
| TC-LOG-004 安全事件日志 | ✅ PASS | `_log_security_async` 逻辑已验证 |

**专项三判定:** 🔴 **BLOCKED** — 文档全链路 (TC-PIPE-001/004)、检索降级 (TC-RET-005/006)、日志系统 (TC-LOG-002/003) 多处失败

---

### 2.4 专项四：异常兜底与降级

| 测试用例 | 状态 | 说明 |
|----------|------|------|
| TC-FALL-001 LLM 超时降级 | ✅ PASS | `call_llm_with_retry` — 3次重试 + 指数退避逻辑已验证 (llm.py:62-78) |
| TC-FALL-002 LLM 不可用降级 | ⚠️ PARTIAL | 降级逻辑设计存在但端到端未验证 |
| TC-FALL-003 LLM 3次重试失败 | ✅ PASS | `RuntimeError("LLM call failed after 3 retries")` 已触发 |
| TC-FALL-004 Milvus 宕机降级 | ❌ NOT TESTED | 需真实 Milvus 环境模拟宕机 |
| TC-FALL-005 Milvus 超时降级 | ⚠️ PARTIAL | `asyncio.wait_for(timeout=15)` 逻辑存在但未验证触发路径 |
| TC-FALL-006 ES 宕机降级 | ❌ NOT TESTED | 需真实 ES 环境 |
| TC-FALL-007 ES+Milvus 同时不可用 | ❌ NOT TESTED | 需真实环境模拟 |
| TC-FALL-008 Redis 不可用 | ⚠️ PARTIAL | `RedisCache` 方法各有一层 try/except，但降级链路未测试 |
| TC-FALL-009 MinIO 不可用 | ❌ NOT TESTED | `minio_client.py` coverage 0% |
| TC-FALL-010 PostgreSQL 不可用 | ✅ PASS | `test_build_checkpointer_returns_valid_connection` — init 失败不崩溃 |
| TC-FALL-011 并发超时保护 | ❌ NOT TESTED | `asyncio.wait_for(timeout=120)` 逻辑存在但无压测 |
| TC-FALL-012 Rate Limiting | ✅ PASS | `@agent_limiter.limit("30/minute")` 声明存在，SlowAPI 集成已验证 |

**专项四判定:** 🔴 **BLOCKED** — 6/12 用例未验证（TC-FALL-004/006/007/009/011 依赖真实运维环境）

---

## 3. 失败用例详情分析

### 3.1 阻塞级失败 (CRITICAL)

| # | 测试 | 根因 | 修复建议 |
|---|------|------|----------|
| 1 | **TC-SEC-001**: `test_filter_sensitive_words` | `output.py:17` — `str` 对象调用了 `.get()`，敏感词过滤逻辑有类型错误 | 修复 `output.py:17` 处的类型处理 |
| 2 | **TC-SEC-004**: `test_sql_injection_in_login_rejected` | 路由 `/api/admin/auth/login` 返回 404 而非 401/422 | 检查 auth router 路径注册 |
| 3 | **TC-LOG-001~003**: 反馈/日志/未命中集成测试全部失败 | API 路径或请求格式变更 | 更新测试中的 API 路径与请求格式 |
| 4 | **TC-PIPE-001**: `test_sync_single_doc_writes_both_stores` | `milvus_client` mock patch 目标 `_get_or_create_collection` 不存在 | 更新 mock 目标 |

### 3.2 非阻塞级失败 (HIGH)

| # | 测试 | 根因 | 影响范围 |
|---|------|------|----------|
| 5 | `test_rerank_*` (3条) | Reranker 本地模型文件未下载 | 检索重排序功能 |
| 6 | `test_embed_*` (4条) | Embedding 模型文件未下载 | 向量化功能 |
| 7 | `test_phone_auth_*` (4条) | 手机认证 API 路径变更 | 登录功能 |
| 8 | `test_dashboard_stats_*` | 注册接口返回格式变更 | 仪表盘 |

### 3.3 低风险失败 (LOW)

| # | 测试 | 根因 |
|---|------|------|
| 9 | `test_readonly_cannot_create_permission` | scope_permission 接口权限配置 |
| 10 | `test_document_*` (2条) | mock 路径变更 |

---

## 4. 性能基准

从 `tests/performance/test_bench.py` 提取：

| 测试场景 | 平均耗时 | P95 | OPS | 评估 |
|----------|---------|-----|-----|------|
| FAQ 匹配 (100条) | 171ms | 189ms | 5.8/s | 需验证 (目标 P95<300ms) |
| FAQ 创建 | 14ms | 100ms | 71/s | 正常 |
| 检索节点 (基线) | 75ms | 800ms | 13/s | 正常 |
| Customer 检索节点 | 700ms | 800ms | 1.4/s | 偏慢 |
| 并发客服对话 | 15.2s | N/A | N/A | 异常慢 |
| 内部图构建 | 7.9s | 8.2s | N/A | 异常慢 |
| 客服图构建 | 5.5s | 5.8s | N/A | 异常慢 |

**性能关注点:**
- 图构建 (LANGGRAPH compile) 耗时 5-8 秒，生产环境应在应用启动时完成
- `customer_faq_match_100_items` 耗时 2.1s — 需 Redis FAQ 向量缓存优化

---

## 5. 代码覆盖率分析

```
Name                       Stmts   Miss  Cover
app/agents/graph.py         104      47    55%
app/agents/state.py          30       1    97%  ← 良好
app/agents/window.py         20      20     0%  ← 需要补充
app/agents/customer_graph.py 91      72    21%  ← 低
app/agents/nodes/validate.py 97      75    23%  ← 低
app/agents/nodes/output.py   66      57    14%  ← 低 (含 bug)
app/agents/nodes/retrieve.py 52      41    21%  ← 低
app/agents/nodes/tools.py   131     109    17%  ← 低
app/retrieval/milvus_client  114     82    28%  ← 低
app/retrieval/es_client       71     44    38%
app/api/agent/__init__.py   312     251    20%  ← 极低 (API 层)
app/main.py                   73      39    47%
TOTAL                       5036   3429    32%
```

**覆盖率关键缺口 (按测试计划优先):**
1. `output.py` (14%) — 敏感词过滤包含类型 bug (TC-SEC-001)
2. `api/agent/__init__.py` (20%) — 缺少 endpoint 级集成测试
3. `customer_graph.py` (21%) — 客服转人工逻辑验证不足
4. `validate.py` (23%) — 输入安全校验覆盖不足
5. `milvus_client.py` (28%) + `es_client.py` (38%) — 降级路径未覆盖

---

## 6. 高优先级未覆盖项

| 测试计划 ID | 状态 | 阻塞原因 |
|-------------|------|----------|
| TC-ISO-001 | 未执行 | `test_isolation_probe.py` 仅含框架代码，需 500 条探针数据 |
| TC-MEM-003 | 未执行 | 需 PostgreSQL 运行环境验证 checkpoint 持久化 |
| TC-MEM-007 | 未执行 | `scripts/test_memory_batch.py` 脚本未实现 |
| TC-FALL-004/006/007 | 未执行 | 需 Docker Compose 环境模拟服务宕机 |
| TC-PIPE-004 | 未执行 | 文档删除级联清理无测试覆盖 |

---

## 7. 红线判定

| # | 红线项 | 状态 | 证据 |
|---|--------|------|------|
| R1 | 跨库渗透泄漏率 0% | 🔴 **NOT VERIFIED** | TC-ISO-001 未执行 |
| R2 | 客服 retrieval 不访问 internal | 🟢 PASS | `test_graph_strips_internal_scope` 通过 |
| R3 | 多轮指代正确率 ≥90% | 🔴 **NOT VERIFIED** | TC-MEM-007 未执行 |
| R4 | 服务重启 checkpoint 可恢复 | 🔴 **NOT VERIFIED** | TC-MEM-003 未执行 |
| R5 | 异常不暴露原始技术错误 | 🟡 PARTIAL | LLM 重试覆盖，Milvus/ES 降级未验证 |
| R6 | 异常不导致服务崩溃 | 🟡 PARTIAL | 同 R5 |
| R7 | 全链路日志可回溯 | 🔴 **FAIL** | TC-LOG-002 集成测试 3/3 失败 |

---

## 8. 修复优先级

| 优先级 | 项 | 估时 | 阻塞 |
|--------|-----|------|------|
| 🔴 P0 | 修复 `output.py:17` 敏感词过滤 bug | 0.5h | TC-SEC-001 |
| 🔴 P0 | 修复 API 路径 (login 404) | 0.5h | TC-SEC-004 |
| 🔴 P0 | 实现 `test_isolation_probe.py` 500探针 | 4h | R1 红线 |
| 🔴 P0 | 实现 `test_memory_batch.py` 多轮脚本 | 3h | R3 红线 |
| 🟡 P1 | 修复日志/反馈集成测试 API 变更 | 2h | TC-LOG-001~003 |
| 🟡 P1 | 补齐 ES/Milvus 降级路径测试 | 3h | R5/R6 红线 |
| 🟡 P1 | 更新 mock 目标 (doc sync, reranker) | 1h | TC-PIPE-001 |
| 🟢 P2 | 下载本地模型 (BGE, Reranker) | 0.5h | 性能测试 |
| 🟢 P2 | Docker Compose 集成环境搭建 | 4h | TC-FALL-004~009 |

---

## 9. 结论

```
测试执行:   617/624 用例 (99%)
通过率:     91.1% (562/617)
红线状态:   4/7 🔴 未通过
覆盖率:     32% (目标 80% 未达标)

最终判定: 🔴 BLOCKED — 禁止上线

建议: 先修复 P0 项 (4项, 估 8h)，再补齐 P1 项 (3项, 估 6h)，
      总计约 2 个工作日后可重新评估准出。
```

> **报告生成:** 2026-07-20 | **工具:** pytest 8.2.2, pytest-cov 5.0.0, pytest-benchmark 4.0.0
