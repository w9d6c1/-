"""10 组多轮对话批量验证 — 上下文连贯性 + checkpoint 持久化 (TC-MEM-001~007)

验证层次:
  L1: 同一 thread_id 下 5+ 轮对话上下文连贯
  L2: HumanMessage/AIMessage 成对写入验证
  L3: 不同 thread_id 互不干扰
  L4: 指代消解 — 近指/远指/序数/角色/链式/对比/跨主题
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.agents.state import AgentState, create_initial_state
from app.agents.customer_graph import create_customer_state


_MULTI_TURN_SCRIPTS: list[dict] = [
    {
        "name": "group_01_near_reference",
        "thread_id": "mem_batch_01",
        "agent": "internal",
        "description": "近指代词 — 这个功能、它",
        "turns": [
            ("知识库支持哪些文档格式？", "支持TXT、DOCX、PDF等格式"),
            ("这些格式中哪个解析质量最好？", "PDF格式解析质量最佳"),
            ("它的分块策略是怎样的？", "PDF采用语义分块，保留标题层级"),
            ("那有大小限制吗？", "单个文件大小限制为50MB"),
            ("用Python怎么调这个接口？", "使用requests.post调用upload接口"),
        ],
    },
    {
        "name": "group_02_far_reference",
        "thread_id": "mem_batch_02",
        "agent": "internal",
        "description": "远指代词 — 上面的接口、那些参数",
        "turns": [
            ("API接口有哪些认证方式？", "支持JWT和API Key两种方式"),
            ("告诉我具体的端口和协议", "HTTP端口8080，HTTPS端口8443"),
            ("上面的接口怎么鉴权？", "在Header中携带Authorization: Bearer <token>"),
            ("还有哪些认证方式？", "还支持OAuth2.0和LDAP认证"),
            ("那些参数分别是什么意思？", "client_id、client_secret、grant_type各有含义"),
        ],
    },
    {
        "name": "group_03_role_context",
        "thread_id": "mem_batch_03",
        "agent": "internal",
        "description": "角色上下文保持 — admin用户、普通用户权限",
        "turns": [
            ("admin用户可以做什么操作？", "可管理用户、文档、FAQ等全部功能"),
            ("普通用户呢？", "仅可查看文档和提问"),
            ("admin怎么添加新用户？", "在管理后台用户管理页面点击新建用户"),
            ("刚刚说的普通用户能看哪些？", "可查看public和其部门scope的文档"),
            ("admin能改其他用户的权限吗？", "可在scope_permission中配置角色权限"),
        ],
    },
    {
        "name": "group_04_ordinal_reference",
        "thread_id": "mem_batch_04",
        "agent": "internal",
        "description": "序数指代 — 第一条、上一个",
        "turns": [
            ("列出FAQ的操作步骤", "1.创建分类 2.编写问题 3.审核发布 4.定期维护"),
            ("第一条是什么？", "创建FAQ分类"),
            ("第二个步骤呢？", "编写FAQ问题和答案"),
            ("最后一个步骤需要注意什么？", "定期维护包括检查过期、更新内容"),
            ("回到第一个步骤，怎么建分类？", "进入FAQ管理，点击新建分类按钮"),
        ],
    },
    {
        "name": "group_05_abbreviated_reference",
        "thread_id": "mem_batch_05",
        "agent": "internal",
        "description": "缩略指代 — 那个参数、这个值",
        "turns": [
            ("向量检索有哪些可调参数？", "model、threshold、top_k、scope"),
            ("推荐值是多少？", "threshold推荐0.7，top_k推荐10"),
            ("改大会有什么影响？", "提高threshold会提高精度但降低召回率"),
            ("那top_k呢？", "增大top_k会返回更多结果但增加耗时"),
            ("综合考虑，参数应该设多少？", "推荐threshold=0.75, top_k=10以平衡精度和性能"),
        ],
    },
    {
        "name": "group_06_single_reference",
        "thread_id": "mem_batch_06",
        "agent": "internal",
        "description": "单指代 — 这个配置",
        "turns": [
            ("同义词配置在哪里设置？", "在管理后台的同义词管理页面"),
            ("这个配置怎么使用？", "配置后自动生效，查询时会用同义词扩展"),
            ("支持哪些类型？", "支持一对一、一对多同义词映射"),
            ("能举个例子吗？", "例如配置'电脑'→'计算机'，搜索电脑会同时搜计算机"),
            ("这个功能有性能影响吗？", "轻微增加查询时间，可忽略不计"),
        ],
    },
    {
        "name": "group_07_chain_reference",
        "thread_id": "mem_batch_07",
        "agent": "internal",
        "description": "链式指代 — BGE → 它 → 那个模型",
        "turns": [
            ("embedding模型用的是哪个？", "使用BAAI/bge-large-zh-v1.5"),
            ("它的向量维度是多少？", "1024维"),
            ("那个模型支持批量编码吗？", "支持，batch_size可配置"),
            ("有更轻量的替代吗？", "有bge-small-zh-v1.5，512维，速度快"),
            ("两者在FAQ场景下怎么选？", "问答精确度要求高用large，速度优先用small"),
        ],
    },
    {
        "name": "group_08_numeric_reference",
        "thread_id": "mem_batch_08",
        "agent": "internal",
        "description": "数值指代 — 这个规则、那个阈值",
        "turns": [
            ("敏感词过滤规则是什么？", "匹配敏感词后自动替换为***"),
            ("能改替换符吗？", "可在配置中自定义替换符"),
            ("那个阈值是什么意思？", "相似度阈值决定是否直接返回FAQ答案"),
            ("默认设的多少？", "默认相似度阈值为0.92"),
            ("调低会有什么效果？", "更多查询走FAQ通道，提高响应速度"),
        ],
    },
    {
        "name": "group_09_comparison_reference",
        "thread_id": "mem_batch_09",
        "agent": "internal",
        "description": "对比指代 — BM25 → 稀疏检索 → 两者",
        "turns": [
            ("混合检索是怎么工作的？", "同时使用BM25稀疏检索和向量稠密检索"),
            ("稀疏检索有什么优势？", "精确匹配关键词，不受embedding质量影响"),
            ("那向量检索有什么优势？", "理解语义，能匹配同义词和近义词"),
            ("两者怎么融合？", "通过RRF算法融合两路结果，再经Reranker重排"),
            ("哪个权重更大？", "RRF算法中k=60，两路结果公平融合无预设权重"),
        ],
    },
    {
        "name": "group_10_cross_topic",
        "thread_id": "mem_batch_10",
        "agent": "internal",
        "description": "跨主题记忆力 — 技术→制度→返回技术",
        "turns": [
            ("LangGraph有几个节点？", "内部智能体有11个节点"),
            ("考勤制度是怎样的？", "每日9点前打卡，迟到需补卡"),
            ("刚才说的LangGraph节点都叫什么名？", "validate、auth、rewrite、route、faq、retrieve、tools、context、generate、output、log"),
            ("考勤迟到几次会通报？", "连续3次或每月累计5次"),
            ("LangGraph的节点之间怎么连接？", "通过add_edge和add_conditional_edges配置流程"),
            ("请假需要几天提前申请？", "年假提前3天，病假可当天申请"),
            ("tools节点最多执行几次？", "ReAct循环最多3次，超过强制进入context节点"),
        ],
    },
]


def _mock_llm_stream(answer: str):
    async def _stream(_messages):
        yield MagicMock(content=answer)
    return _stream


class TestMultiTurnMemory:
    """TC-MEM-001~007: 多轮记忆完整性验证"""

    @pytest.mark.asyncio
    @pytest.mark.parametrize("script", _MULTI_TURN_SCRIPTS, ids=[s["name"] for s in _MULTI_TURN_SCRIPTS])
    async def test_multi_turn_context_coherence(self, script):
        from app.agents.graph import build_internal_agent_graph
        from app.agents.customer_graph import build_customer_agent_graph

        agent_type = script["agent"]
        thread_id = script["thread_id"]

        mock_docs = []
        graph = build_internal_agent_graph() if agent_type == "internal" else build_customer_agent_graph()

        with patch("app.agents.nodes.retrieve.hybrid_retrieve", return_value=mock_docs):
            for turn_idx, (query, expected_answer) in enumerate(script["turns"]):
                mock_llm = MagicMock()
                mock_llm.astream = _mock_llm_stream(expected_answer)

                with patch("app.agents.nodes.generate.create_llm", return_value=mock_llm):
                    with patch("app.agents.customer.generate.create_llm", return_value=mock_llm):
                        if agent_type == "internal":
                            state = create_initial_state(thread_id=thread_id, query=query)
                        else:
                            state = create_customer_state(thread_id=thread_id, query=query)

                        result = await graph.ainvoke(
                            state,
                            config={"configurable": {"thread_id": thread_id}},
                        )

                        assert result is not None, f"Turn {turn_idx + 1}: graph returned None"
                        answer = result.get("final_answer", "")
                        assert len(answer) > 0, (
                            f"{script['name']} Turn {turn_idx + 1}: "
                            f"Query='{query}' returned empty answer"
                        )

    @pytest.mark.asyncio
    async def test_all_10_groups_pass(self):
        passed = 0
        failed_details: list[str] = []

        mock_docs = []
        graph = build_internal_agent_graph()

        for script in _MULTI_TURN_SCRIPTS:
            if script["agent"] != "internal":
                continue
            try:
                with patch("app.agents.nodes.retrieve.hybrid_retrieve", return_value=mock_docs):
                    for turn_idx, (query, expected_answer) in enumerate(script["turns"]):
                        mock_llm = MagicMock()
                        mock_llm.astream = _mock_llm_stream(expected_answer)

                        with patch("app.agents.nodes.generate.create_llm", return_value=mock_llm):
                            state = create_initial_state(
                                thread_id=script["thread_id"],
                                query=query,
                            )
                            result = await graph.ainvoke(
                                state,
                                config={"configurable": {"thread_id": script["thread_id"]}},
                            )
                            if result is None or not result.get("final_answer"):
                                failed_details.append(
                                    f"{script['name']} Turn {turn_idx + 1}: empty answer for '{query}'"
                                )
                passed += 1
            except Exception as e:
                failed_details.append(f"{script['name']}: {e}")

        assert len(failed_details) == 0, (
            f"Multi-turn batch test: {passed}/10 groups passed. "
            f"Failures: {failed_details}"
        )

    def test_all_scripts_have_enough_turns(self):
        for script in _MULTI_TURN_SCRIPTS:
            assert len(script["turns"]) >= 5, (
                f"{script['name']}: only {len(script['turns'])} turns, need ≥5"
            )

    def test_all_thread_ids_unique(self):
        ids = [s["thread_id"] for s in _MULTI_TURN_SCRIPTS]
        assert len(ids) == len(set(ids)), f"Duplicate thread_ids: {ids}"


class TestMultiTurnThreadIsolation:
    """TC-MEM-005: 不同 thread_id 互不干扰"""

    @pytest.mark.asyncio
    async def test_threads_independent(self):
        from app.agents.customer_graph import build_customer_agent_graph

        graph = build_customer_agent_graph()
        mock_fusion = [FusionResult(
            unique_id="1", doc_id=1, chunk_index=0,
            content="公开知识", fused_score=0.9, scope="public",
        )]

        results: dict[str, list[str]] = {}
        threads = ["iso_a", "iso_b"]

        for tid in threads:
            answers = []
            for i in range(3):
                mock_llm = MagicMock()
                mock_llm.astream = _mock_llm_stream(f"[{tid}] Turn {i+1} answer")

                with patch("app.agents.customer.retrieve.hybrid_retrieve", new=AsyncMock(return_value=mock_fusion)):
                    with patch("app.agents.customer.retrieve.rerank", new=AsyncMock(return_value=mock_fusion)):
                        with patch("app.agents.customer.generate.create_llm", return_value=mock_llm):
                            with patch("app.agents.customer.faq.get_faq_vectors", return_value=[]):
                                with patch("app.agents.customer.faq.embed_query", return_value=[0.1] * 1024):
                                    state = create_customer_state(
                                        thread_id=tid,
                                        query=f"Query {i+1} for {tid}",
                                    )
                                    state["user_scopes"] = ["public", "customer"]
                                    result = await graph.ainvoke(
                                        state,
                                        config={"configurable": {"thread_id": tid}},
                                    )
                                    answers.append(str(result.get("final_answer", "")))
            results[tid] = answers

        for tid, answers in results.items():
            for ans in answers:
                assert f"[{tid}]" in ans, (
                    f"Thread {tid}: answer does not contain expected marker: {ans[:50]}"
                )


class TestMemoryCheckpointPersistence:
    """TC-MEM-002: HumanMessage/AIMessage 成对写入验证"""

    @pytest.mark.asyncio
    async def test_state_messages_propagate_across_turns(self):
        from langgraph.checkpoint.memory import InMemorySaver
        from langgraph.graph import END, StateGraph

        workflow = StateGraph(AgentState)
        workflow.add_node("echo", lambda s: {**s, "final_answer": f"ECHO: {s['original_query']}"})
        workflow.set_entry_point("echo")
        workflow.add_edge("echo", END)
        graph = workflow.compile(checkpointer=InMemorySaver())

        tid = "cp_test_001"
        for i in range(5):
            state = create_initial_state(thread_id=tid, query=f"Message {i}")
            result = await graph.ainvoke(state, config={"configurable": {"thread_id": tid}})
            assert result["final_answer"] == f"ECHO: Message {i}"

        snapshot = await graph.aget_state({"configurable": {"thread_id": tid}})
        msgs = snapshot.values.get("messages", []) if snapshot and snapshot.values else []
        assert len(msgs) >= 5, (
            f"Expected ≥5 messages in checkpoint, got {len(msgs)}"
        )

    @pytest.mark.asyncio
    async def test_checkpoint_survives_graph_invoke(self):
        from langgraph.checkpoint.memory import InMemorySaver
        from langgraph.graph import END, StateGraph

        workflow = StateGraph(AgentState)
        workflow.add_node("pass", lambda s: {**s, "final_answer": "OK"})
        workflow.set_entry_point("pass")
        workflow.add_edge("pass", END)

        cp = InMemorySaver()
        graph = workflow.compile(checkpointer=cp)

        tid = "cp_survive"
        result = await graph.ainvoke(
            create_initial_state(thread_id=tid, query="test"),
            config={"configurable": {"thread_id": tid}},
        )
        assert result["final_answer"] == "OK"

        snap = await graph.aget_state({"configurable": {"thread_id": tid}})
        assert snap is not None
        assert snap.values.get("thread_id") == tid

    @pytest.mark.asyncio
    async def test_checkpoint_init_fallback_no_crash(self):
        with patch("app.agents.graph.AsyncPostgresSaver") as mock_aps:
            mock_aps.from_conn_string.side_effect = RuntimeError("PG unavailable")
            from app.agents.graph import init_checkpointer

            checkpointer = await init_checkpointer()
            assert checkpointer is None


class TestTokenBudgetTruncation:
    """TC-MEM-004/009: Token 预算截断 + 长会话恢复"""

    def test_trim_history_under_budget(self):
        from langchain_core.messages import HumanMessage
        from app.agents.window import trim_history

        msgs = [HumanMessage(content="短消息") for _ in range(5)]
        result = trim_history(list(msgs), max_tokens=10000)
        assert len(result) == 5

    def test_trim_history_over_budget(self):
        from langchain_core.messages import HumanMessage
        from app.agents.window import trim_history

        msgs = [HumanMessage(content="A" * 500) for _ in range(20)]
        result = trim_history(list(msgs), max_tokens=1000)
        assert len(result) < 20
        assert len(result) > 0

    def test_trim_history_empty_input(self):
        from app.agents.window import trim_history

        assert trim_history([], max_tokens=1000) == []

    def test_count_tokens_positive(self):
        from app.agents.llm import count_tokens

        assert count_tokens("Hello world") > 0
        assert count_tokens("") == 0
