# 9号测试 — AI 智能体核心能力验收报告

> **验收依据**: `C:\Users\TLD\Desktop\知识库\9号测试.md`
> **对应阶段**: 开发计划「阶段三」AI 能力层
> **验收日期**: YYYY-MM-DD
> **执行人**: _______

---

## 一、双智能体基础能力

### 1.1 内部问答智能体

| 属性 | 内容 |
|------|------|
| **操作方式** | 员工身份调用内部接口，提问内部制度/技术文档类问题 |
| **验收标准** | (1) 可检索到 internal + public 范围知识 (2) 回答标注引用来源 (3) 支持多轮上下文延续 |
| **测试文件** | `tests/unit/test_graph.py` `tests/e2e/test_full_pipeline.py` |
| **执行命令** | `docker compose exec backend python -m pytest tests/unit/test_graph.py tests/e2e/test_full_pipeline.py -v` |
| **测试结果** | ☐ PASS / ☐ FAIL |
| **实际表现** | ___________ |
| **备注** | ___________ |

### 1.2 客服问答智能体

| 属性 | 内容 |
|------|------|
| **操作方式** | 调用客服接口，提问产品/售后类问题 |
| **验收标准** | (1) 仅返回 customer + public 范围知识 (2) 高置信直接回答，低置信引导转人工 (3) FAQ 命中直接返回标准答案 |
| **测试文件** | `tests/unit/test_customer.py` `tests/integration/test_customer_chat.py` |
| **执行命令** | `docker compose exec backend python -m pytest tests/unit/test_customer.py tests/integration/test_customer_chat.py -v` |
| **测试结果** | ☐ PASS / ☐ FAIL |
| **实际表现** | ___________ |
| **备注** | ___________ |

---

## 二、RAG 检索全链路

### 2.1 FAQ 精准匹配

| 属性 | 内容 |
|------|------|
| **操作方式** | 输入 FAQ 标准问题、相似问句 |
| **验收标准** | (1) 相似度 ≥0.92 直接返回标准答案，不调用 LLM (2) 单条响应耗时 < 300ms |
| **测试文件** | `tests/unit/test_faq_node.py` `tests/performance/test_bench.py` |
| **执行命令** | `docker compose exec backend python -m pytest tests/unit/test_faq_node.py -v` |
| **性能验证** | `docker compose exec backend python -m pytest tests/performance/test_bench.py -k faq --benchmark-only -v` |
| **功能测试** | ☐ PASS / ☐ FAIL |
| **P95 延迟** | ___________ (目标 < 300ms) |
| **实际表现** | ___________ |
| **备注** | ___________ |

### 2.2 混合检索流程

| 属性 | 内容 |
|------|------|
| **操作方式** | 提问长文档细节问题，查看检索日志 |
| **验收标准** | BM25 稀疏召回 + 向量稠密召回双路并行、RRF 融合、Reranker 重排全链路正常执行 |
| **测试文件** | `tests/unit/test_fusion.py` `tests/unit/test_reranker.py` |
| **执行命令** | `docker compose exec backend python -m pytest tests/unit/test_fusion.py tests/unit/test_reranker.py -v` |
| **测试结果** | ☐ PASS / ☐ FAIL |
| **BM25 召回数** | ___________ |
| **Dense 召回数** | ___________ |
| **RRF 融合数** | ___________ |
| **Reranker 重排后** | ___________ |
| **备注** | ___________ |

### 2.3 分块策略适配

| 属性 | 内容 |
|------|------|
| **操作方式** | 分别上传制度文档、技术文档、通用长文档 |
| **验收标准** | 不同类型文档自动匹配对应切片策略；代码块、标题层级保留完整 |
| **测试文件** | `tests/unit/test_loader.py` `tests/unit/test_document_chunks.py` |
| **执行命令** | `docker compose exec backend python -m pytest tests/unit/test_loader.py tests/unit/test_document_chunks.py -v` |
| **测试结果** | ☐ PASS / ☐ FAIL |
| **实际表现** | ___________ |
| **已实现策略** | fixed / recursive / semantic (3 种) |
| **备注** | ___________ |

---

## 三、LangGraph 流程与交互能力

### 3.1 节点流程完整性

| 属性 | 内容 |
|------|------|
| **操作方式** | 开启 debug 模式，发起一轮完整对话 |
| **验收标准** | 按顺序执行全部 11 个节点；每个节点状态可追溯 |
| **节点顺序** | 输入校验 → 鉴权 → 路由分发 → FAQ匹配 → 混合检索 → 生成 → 输出校验 → 日志记录 |
| **测试文件** | `tests/unit/test_graph_complete.py` `tests/e2e/test_full_pipeline.py` |
| **执行命令** | `docker compose exec backend python -m pytest tests/unit/test_graph_complete.py tests/e2e/test_full_pipeline.py -v` |
| **测试结果** | ☐ PASS / ☐ FAIL |
| **实际表现** | ___________ |
| **备注** | ___________ |

### 3.2 多轮上下文

| 属性 | 内容 |
|------|------|
| **操作方式** | 连续多轮提问，使用指代描述（如"它的参数是什么"） |
| **验收标准** | (1) 可正确理解指代，上下文连贯 (2) 服务重启后，历史会话通过 thread_id 可完整恢复 |
| **测试文件** | `tests/unit/test_cache_window.py` `tests/unit/test_customer_nodes.py` |
| **执行命令** | `docker compose exec backend python -m pytest tests/unit/test_cache_window.py tests/unit/test_customer_nodes.py -v` |
| **测试结果** | ☐ PASS / ☐ FAIL |
| **实际表现** | ___________ |
| **备注** | ___________ |

### 3.3 转人工决策（客服）

| 属性 | 内容 |
|------|------|
| **触发条件** | (1) 低相似度检索 (2) 转人工关键词 (3) 连续 2 轮表达不满 (4) 模型输出转接标记 |
| **验收标准** | 命中任一条件即输出转接话术；对话摘要推送至人工队列；转人工事件记入日志 |
| **测试文件** | `tests/unit/test_customer.py` |
| **执行命令** | `docker compose exec backend python -m pytest tests/unit/test_customer.py -v` |
| **测试结果** | ☐ PASS / ☐ FAIL |
| **实际表现** | ___________ |
| **备注** | ___________ |

### 3.4 工具调用（内部）

| 属性 | 内容 |
|------|------|
| **操作方式** | 触发工具类问题（如对接 OA/CRM 查询） |
| **验收标准** | ReAct 循环正常执行；工具返回结果注入上下文；最终回答包含工具返回数据 |
| **测试文件** | `tests/unit/test_tools_node.py` |
| **执行命令** | `docker compose exec backend python -m pytest tests/unit/test_tools_node.py -v` |
| **测试结果** | ☐ PASS / ☐ FAIL |
| **实际表现** | ___________ |
| **备注** | 当前仅实现 search_kb / decompose 两个内部工具，外部 API 工具（订单/工单查询）已搁置 |

### 3.5 Token 窗口管理

| 属性 | 内容 |
|------|------|
| **操作方式** | 输入超长提问 + 多轮历史对话 |
| **验收标准** | 自动按预算截断、压缩历史对话；不会触发模型 Token 超限报错 |
| **测试文件** | `tests/unit/test_cache_window.py` |
| **执行命令** | `docker compose exec backend python -m pytest tests/unit/test_cache_window.py -v` |
| **测试结果** | ☐ PASS / ☐ FAIL |
| **实际表现** | ___________ |
| **备注** | ___________ |

---

## 汇总

| # | 检查项 | 结果 | 备注 |
|---|--------|------|------|
| 1 | 内部问答智能体 | ☐ | |
| 2 | 客服问答智能体 | ☐ | |
| 3 | FAQ 精准匹配 | ☐ | |
| 4 | 混合检索流程 | ☐ | |
| 5 | 分块策略适配 | ☐ | |
| 6 | 节点流程完整性 | ☐ | |
| 7 | 多轮上下文 | ☐ | |
| 8 | 转人工决策 | ☐ | |
| 9 | 工具调用 | ☐ | |
| 10 | Token 窗口管理 | ☐ | |

**总计**: __ / 10 项通过

## 执行记录

| 项目 | 内容 |
|------|------|
| 执行时间 | ___________ |
| 完成时间 | ___________ |
| 总耗时 | ___________ |
| 环境状态 | Docker: ☐ 运行中 / ☐ 已停止 |

---

> 本报告模板对应 9号测试.md 全部 10 个检查项。执行后可运行 `scripts\run_acceptance_ai.ps1` 自动生成填充结果。
