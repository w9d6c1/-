# LangGraph 节点说明文档

## 内部智能体 (Internal Agent)

**入口**: `/api/agent/internal/chat`
**图文件**: `backend/app/agents/graph.py`
**11 节点**, 编排模式：条件分支 + ReAct 循环

### 节点流程图

```
START
  │
  ▼
[1] validate_input  ← 输入校验
  │
  ▼
[2] auth            ← 身份鉴权 + scope 映射
  │
  ▼
[3] rewrite         ← 查询改写（多轮合并/同义词）
  │
  ▼
[4] route           ← 路由决策 (FAQ / RAG / reject)
  │
  ├── route=faq ──→ [5a] faq_match ──→ [9] output ──→ [10] log ──→ END
  │                      FAQ 精准匹配      输出校验      日志记录
  │
  └── route=retrieve ──→ [5] retrieve ──→ [6] tools ──→ [7] context ──→ [8] generate ──→ [9] output ──→ [10] log ──→ END
                           混合检索       工具决策      上下文组装     答案生成         输出校验        日志记录
                                                  │
                                                  └── has_tool_calls ∧ iteration < 3 ──→ [5] retrieve (循环)
```

### 节点详细说明

#### 1. validate_input — 输入校验

| 属性 | 内容 |
|------|------|
| **文件** | `backend/app/agents/nodes/validate.py` |
| **功能** | 检测 SQL 注入、Prompt 注入、禁答词、空查询 |
| **输入** | `state["messages"]` (最后一条用户消息) |
| **输出** | `is_blocked: bool`, `block_reason: str` |
| **阻断条件** | SQL 注入正则匹配 / Prompt 注入关键词 / 禁答词命中 / 查询为空 |

#### 2. auth — 身份鉴权

| 属性 | 内容 |
|------|------|
| **文件** | `backend/app/agents/nodes/auth.py` |
| **功能** | 解析 JWT token，加载用户角色，映射 scope 权限 |
| **输入** | request header `Authorization` |
| **输出** | `user_id`, `user_role`, `user_department`, `user_scopes` |
| **Scope 映射** | superadmin → [public, internal, customer] / readonly → [public] |

#### 3. rewrite — 查询改写

| 属性 | 内容 |
|------|------|
| **文件** | `backend/app/agents/nodes/rewrite.py` |
| **功能** | (1) 多轮对话历史合并 (2) 指代消解 (3) 同义词扩展 |
| **输入** | `messages` (含历史) + `original_query` |
| **输出** | `rewritten_query` |
| **LLM 调用** | 是 (DeepSeek, max_retries=2) |

#### 4. route — 路由分发

| 属性 | 内容 |
|------|------|
| **文件** | `backend/app/agents/nodes/route.py` |
| **功能** | 根据查询长度和特征决定走 FAQ 匹配还是 RAG 检索 |
| **输出** | `route: "faq" | "retrieve" | "reject"` |
| **规则** | 短查询(<10字) → FAQ; 长查询 → RAG; 空查询 → reject |

#### 5. retrieve — 混合检索

| 属性 | 内容 |
|------|------|
| **文件** | `backend/app/agents/nodes/retrieve.py` |
| **功能** | BM25 稀疏召回 + 向量稠密召回 → RRF 融合 → Reranker 重排 |
| **输入** | `rewritten_query`, `user_scopes` |
| **输出** | `retrieved_docs: list[FusionResult]` |
| **流程** | ES查询(scope索引) ∥ Milvus查询(scope Collection) → `fusion.py` (RRF k=60) → `reranker.py` (Top-N) |

#### 6. tools — 工具调用 (ReAct)

| 属性 | 内容 |
|------|------|
| **文件** | `backend/app/agents/nodes/tools.py` |
| **功能** | ReAct 循环：判断是否需要工具 → 调用工具 → 注入结果 |
| **工具列表** | `search_knowledge_base` (结构化搜索), `decompose_and_search` (子问题拆分) |
| **循环上限** | 最大 3 次 iteration |
| **输出** | `retrieved_docs` (追加工具返回结果) |

#### 7. context — 上下文组装

| 属性 | 内容 |
|------|------|
| **文件** | `backend/app/agents/nodes/context.py` |
| **功能** | 将检索文档 + 历史消息组装为 LLM prompt 上下文 |
| **Token 限制** | 最大 3000 tokens，超过时按优先级截断 |
| **输出** | `context: str` |

#### 8. generate — 答案生成

| 属性 | 内容 |
|------|------|
| **文件** | `backend/app/agents/nodes/generate.py` |
| **功能** | 调用 LLM 生成最终答案，标注引用来源 |
| **LLM 调用** | 是 (DeepSeek, max_retries=3, 指数退避 1s/2s/4s) |
| **输出** | `final_answer: str`, `confidence: float` |

#### 9. output — 输出校验

| 属性 | 内容 |
|------|------|
| **文件** | `backend/app/agents/nodes/output.py` |
| **功能** | (1) 敏感词过滤/脱敏 (2) 置信度标记 (3) 合规校验 |
| **输出** | `is_compliant: bool`, `compliance_issues: list[str]` |

#### 10. log — 日志记录

| 属性 | 内容 |
|------|------|
| **文件** | `backend/app/agents/nodes/logging.py` |
| **功能** | 记录对话全链路到 chat_log 表 |
| **写入** | `thread_id`, `question`, `answer`, `node_name`, `node_latency_ms`, `hit_faq_id`, `hit_chunk_ids` |

---

## 客服智能体 (Customer Agent)

**入口**: `/api/agent/customer/chat`
**图文件**: `backend/app/agents/customer_graph.py`
**6 节点**, 无工具调用 + 有人工转接

### 特殊节点

#### customer_route_node — 路由分发 (客服版)

| 属性 | 内容 |
|------|------|
| **文件** | `backend/app/agents/customer_graph.py` |
| **功能** | 先调 `_strip_internal_scopes()` 剥离 internal scope，再路由 |

#### customer_faq_match_node — FAQ 匹配 (客服版)

| 属性 | 内容 |
|------|------|
| **文件** | `backend/app/agents/customer/faq.py` |
| **功能** | 硬编码仅匹配 `["public", "customer"]` scope 的 FAQ |

#### human_handoff_node — 转人工决策

| 属性 | 内容 |
|------|------|
| **文件** | `backend/app/agents/customer_graph.py` |
| **功能** | 4 类触发条件：低相似度检索 / 转人工关键词 / 连续 2 轮表达不满 / 模型输出转接标记 |
| **输出** | `needs_human: bool`, `human_reason: str`, 对话摘要推送人工队列 |

---

## 状态管理

| 属性 | 内容 |
|------|------|
| **State 定义** | `backend/app/agents/state.py` — `AgentState` TypedDict (30+ 字段) |
| **Checkpointer** | `PostgresSaver` (连接 PostgreSQL) |
| **会话恢复** | 通过 `thread_id` 恢复完整历史 |

## API 端点

| 端点 | 方法 | 智能体 | 备注 |
|------|------|--------|------|
| `/api/agent/internal/chat` | POST | 内部 | 限流 30/min |
| `/api/agent/internal/chat/stream` | POST | 内部 | SSE 流式 |
| `/api/agent/customer/chat` | POST | 客服 | 限流 60/min |
| `/api/agent/customer/chat/stream` | POST | 客服 | SSE 流式 |
| `/api/agent/rewrite` | POST | 工具 | 查询改写测试 |
| `/api/agent/status` | GET | 通用 | 健康检查 |
| `/api/agent/info` | GET | 通用 | 模块状态 |

## 安全防护

| 层级 | 机制 | 文件 |
|------|------|------|
| 向量层 | 三 Collection 物理隔离 | `milvus_client.py` |
| 路由层 | `_strip_internal_scopes` 强制剥离 interval | `customer_graph.py` |
| 接口层 | JWT + `require_auth` 依赖 | `dependencies.py` |
| 输入层 | SQL注入/Prompt注入/禁答词拦截 | `validate.py` |
| 输出层 | 敏感词脱敏 + 置信度标记 | `output.py` |
| 日志层 | 全链路审计 + 安全事件记录 | `logging.py` |
