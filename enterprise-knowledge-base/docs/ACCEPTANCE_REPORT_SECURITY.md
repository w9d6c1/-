# 10号测试 — 安全隔离 + 性能稳定性验收报告

> **验收依据**: `C:\Users\TLD\Desktop\知识库\10号.md`
> **对应阶段**: 开发计划「阶段四」测试验证 + 安全红线
> **验收日期**: YYYY-MM-DD
> **执行人**: _______

---

## 三、安全隔离专项验收（核心红线）

### 3.1 向量层物理隔离

| 属性 | 内容 |
|------|------|
| **操作方式** | 分别上传三类 scope 的文档；查看 Milvus 三个 Collection 的向量数量 |
| **验收标准** | 仅对应 Collection 向量增长，无交叉写入；三个 Collection 独立配置、独立访问权限 |
| **测试文件** | `tests/unit/test_milvus_client.py` |
| **执行命令** | `docker compose exec backend python -m pytest tests/unit/test_milvus_client.py -v` |
| **结果** | ☐ PASS / ☐ FAIL |
| **Collection 状态** | coll_public: _____ / coll_internal: _____ / coll_customer: _____ |
| **备注** | ___________ |

### 3.2 路由层流程隔离

| 属性 | 内容 |
|------|------|
| **操作方式** | 用客服身份提问内部敏感关键词；查看检索执行日志 |
| **验收标准** | 客服请求仅执行 customer + public 集合的检索代码路径，完全不触达 internal 集合的查询逻辑 |
| **测试文件** | `tests/unit/test_customer.py` `tests/security/test_isolation_probe.py` |
| **执行命令** | `docker compose exec backend python -m pytest tests/unit/test_customer.py tests/security/test_isolation_probe.py -v` |
| **结果** | ☐ PASS / ☐ FAIL |
| **覆盖验证** | L1: create_customer_state 硬编码 scope / L2: _strip_internal_scopes / L3: customer_route_node / L4: customer_retrieve_node |
| **备注** | ___________ |

### 3.3 跨库泄漏渗透测试（500 条探针）

| 属性 | 内容 |
|------|------|
| **操作方式** | 执行 500 条探针用例（客服身份模拟查询内部知识） |
| **验收标准** | 跨库隔离泄漏率 0%；无任何内部知识片段被客服智能体返回 |
| **测试文件** | `tests/security/test_isolation_probe.py` |
| **执行命令** | `docker compose exec backend python -m pytest tests/security/test_isolation_probe.py -v` |
| **结果** | ☐ PASS / ☐ FAIL |
| **覆盖层次** | L1: State 构造 / L2: Strip 函数 / L3: Route 节点 / L4: Retrieve 节点 / L5: Attack向量(注入/边界) |
| **备注** | 当前为代码层+状态层隔离验证（553行），真正 HTTP 级别 500 探针需额外脚本 |

### 3.4 输入输出安全校验

| 属性 | 内容 |
|------|------|
| **操作方式** | 输入 SQL 注入、Prompt 注入语句；构造含敏感词的输出场景 |
| **验收标准** | 输入侧恶意内容被拦截；输出侧敏感词被过滤/脱敏；安全事件记入日志 |
| **测试文件** | `tests/unit/test_state_validate.py` `tests/unit/test_safety_words.py` `tests/security/test_sensitive_accuracy.py` |
| **执行命令** | `docker compose exec backend python -m pytest tests/unit/test_state_validate.py tests/unit/test_safety_words.py tests/security/test_sensitive_accuracy.py -v` |
| **结果** | ☐ PASS / ☐ FAIL |
| **输入覆盖** | SQL 注入 / Prompt 注入 / 禁答词 / 空查询 |
| **输出覆盖** | 敏感词过滤 / 脱敏 / 置信度标记 / 合规校验 |
| **敏感词拦截率** | _____ (目标 ≥99%) |
| **备注** | ___________ |

### 3.5 接口权限隔离

| 属性 | 内容 |
|------|------|
| **操作方式** | 用客服 API Key 调用内部问答接口；无 Token 访问内部接口 |
| **验收标准** | 返回 403/401；鉴权失败无法获取任何知识数据 |
| **测试文件** | `tests/unit/test_auth_guard.py` `tests/unit/test_dept_isolation.py` |
| **执行命令** | `docker compose exec backend python -m pytest tests/unit/test_auth_guard.py tests/unit/test_dept_isolation.py -v` |
| **结果** | ☐ PASS / ☐ FAIL |
| **验证范围** | readonly 用户 403 / 缺失 Token 401 / 部门隔离 |
| **备注** | ___________ |

### 3.6 个人信息脱敏

| 属性 | 内容 |
|------|------|
| **操作方式** | 对话中输入手机号、身份证号等个人信息 |
| **验收标准** | 输出内容自动脱敏打码；日志中敏感信息同样做脱敏处理 |
| **测试文件** | `tests/unit/test_safety_words.py` |
| **执行命令** | `docker compose exec backend python -m pytest tests/unit/test_safety_words.py -v` |
| **结果** | ☐ PASS / ☐ FAIL |
| **实际表现** | ___________ |
| **备注** | ___________ |

---

## 四、性能与稳定性验收

### 4.1 基础响应耗时

| 属性 | 内容 |
|------|------|
| **操作方式** | 单用户连续发起 FAQ、RAG 两类请求，统计端到端耗时 |
| **验收标准** | FAQ 场景 P95 < 300ms；RAG 场景 P95 < 3s（非流式）；流式首字延迟 < 1s |
| **测试文件** | `tests/performance/test_bench.py` |
| **执行命令** | `docker compose exec backend python -m pytest tests/performance/test_bench.py --benchmark-only -v` |
| **结果** | ☐ PASS / ☐ FAIL |
| **FAQ P95** | _____ (目标 < 300ms) |
| **RAG P95** | _____ (目标 < 3s) |
| **并发 20 QPS** | _____ (目标不超时) |
| **备注** | benchmark 结果需查看命令行输出，非 PASS/FAIL 二值判定 |

### 4.2 异常降级兜底 ⚠️ 手动验证

| 属性 | 内容 |
|------|------|
| **操作方式** | 分别关闭大模型服务、向量库服务，发起对话请求 |
| **验收标准** | 大模型不可用时降级返回检索摘要；向量库故障时降级为 BM25 检索；不抛出 500 原始错误 |
| **自动化** | ❌ 无自动化测试 |

**手动操作步骤**：

```
# 1. 停止 LLM 服务（模拟大模型不可用）
#    设置一个无效的 LLM_API_KEY 后重启后端
#    docker compose exec backend python -m pytest ... (使用 mock)

# 2. 停止向量库（模拟向量库故障）
docker compose stop milvus

# 3. 发起对话请求检查降级行为
curl -X POST http://localhost:8000/api/agent/internal/chat \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <token>" \
  -d '{"query":"考勤制度", "thread_id":"test_degrade_1"}'
# 预期：降级返回 BM25 检索结果或检索摘要，而非 500 错误

# 4. 恢复服务
docker compose start milvus
```

| **LLM 降级** | ☐ PASS / ☐ FAIL | 实际返回: _____ |
| **向量库降级** | ☐ PASS / ☐ FAIL | 实际返回: _____ |
| **备注** | ___________ |

### 4.3 超时与熔断 ⚠️ 手动验证

| 属性 | 内容 |
|------|------|
| **操作方式** | 模拟外部工具超时、模型接口超时 |
| **验收标准** | 超过超时阈值自动中断；失败自动重试 2 次（指数退避）；连续失败触发熔断，返回标准化降级话术 |
| **代码依据** | `backend/app/agents/llm.py` — `call_llm_with_retry` (3次重试，指数退避 1s/2s/4s) |
| **自动化** | ⚠️ 仅有 LLM 配置测试，无重试/熔断专项测试 |

**手动验证要点**：

```
1. 确认 llm.py 中 retry 逻辑：
   - max_retries 默认为 3
   - 指数退避：delay = min(1000 * 2^i, 8000) / 1000 (1s, 2s, 4s)
   - 全部失败抛出 RuntimeError

2. 确认 rewrite.py 中调用：
   - acall_llm_with_retry(llm, msgs, max_retries=2)

3. 确认后端日志中：
   - 重试时输出 llm_retry_attempt 警告
   - 重试耗尽后输出错误日志
```

| **重试逻辑** | ☐ 已验证 / ☐ 未验证 |
| **指数退避** | ☐ 已验证 / ☐ 未验证 |
| **熔断话术** | ☐ 已验证 / ☐ 未验证 |
| **备注** | ___________ |

### 4.4 基础并发验证

| 属性 | 内容 |
|------|------|
| **操作方式** | 用压测工具模拟 10 QPS 并发，持续运行 1 分钟 |
| **验收标准** | 服务无崩溃、无内存泄漏；请求错误率 < 1% |
| **测试文件** | `tests/performance/test_bench.py` — `test_concurrent_chat_requests` / `test_concurrent_customer_chat` |
| **执行命令** | `docker compose exec backend python -m pytest tests/performance/test_bench.py --benchmark-only -v` |
| **结果** | ☐ PASS / ☐ FAIL |
| **错误率** | _____ (目标 < 1%) |
| **备注** | ___________ |

---

## 汇总

| # | 检查项 | 结果 | 类型 |
|---|--------|------|------|
| 1 | 向量层物理隔离 | ☐ | 自动化 |
| 2 | 路由层流程隔离 | ☐ | 自动化 |
| 3 | 跨库泄漏渗透测试 | ☐ | 自动化 |
| 4 | 输入输出安全校验 | ☐ | 自动化 |
| 5 | 接口权限隔离 | ☐ | 自动化 |
| 6 | 个人信息脱敏 | ☐ | 自动化 |
| 7 | 基础响应耗时 | ☐ | 半自动(benchmark) |
| 8 | 异常降级兜底 | ☐ | 手动 |
| 9 | 超时与熔断 | ☐ | 手动 |
| 10 | 基础并发验证 | ☐ | 半自动(benchmark) |

**总计**: __ / 10 项通过
**自动化**: 6 项  | **半自动**: 2 项  | **手动**: 2 项

## 执行记录

| 项目 | 内容 |
|------|------|
| 执行时间 | ___________ |
| 完成时间 | ___________ |
| 总耗时 | ___________ |
| 环境状态 | Docker: ☐ 运行中 / ☐ 已停止 |

---

> 本报告模板对应 10号.md 全部 10 个检查项。执行后可运行 `scripts\run_acceptance_security.ps1` 自动执行 8 项测试（2 项手动除外）。
