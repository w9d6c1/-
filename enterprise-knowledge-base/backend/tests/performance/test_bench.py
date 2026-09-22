"""性能基准测试 — FAQ匹配 / RAG检索 / API吞吐 / 文档分块

指标目标:
  - FAQ 匹配 P95 < 200ms (100 条 FAQ)
  - RAG 问答 P95 < 3s (30 条混合问题)
  - 并发 20 QPS 不超时
  - 文档分块+向量化 < 5s/MB

运行: python -m pytest tests/performance/ --benchmark-only
"""

import asyncio
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.agents.state import AgentState


@pytest.fixture
def _init_state():
    from langchain_core.messages import HumanMessage

    return {
        "messages": [HumanMessage(content="测试")],
        "thread_id": "bench_test",
        "user_id": 1,
        "user_role": "superadmin",
        "user_department": None,
        "user_scopes": ["public"],
        "original_query": "测试查询",
        "rewritten_query": "",
        "is_blocked": False,
        "block_reason": "",
        "faq_hit": False,
        "faq_answer": None,
        "retrieved_docs": [],
        "context": "",
        "final_answer": "",
        "is_compliant": True,
        "compliance_issues": [],
        "confidence": 0.0,
        "needs_human": False,
        "human_reason": "",
        "route": "",
        "iteration": 0,
        "error": None,
    }


# ================================================================
# FAQ 匹配延迟基准
# ================================================================
class TestFAQMatchLatency:
    def test_faq_match_with_100_items(self, benchmark, _init_state):
        from app.agents.nodes.faq import faq_match_node

        mock_vec = [0.1] * 1024
        faq_vectors = []
        for i in range(100):
            faq_vectors.append({
                "faq_id": i,
                "question": f"问题{i}",
                "content": f"答案{i}",
                "scope": "public",
                "vector": [0.5] * 1024,
            })

        with patch("app.agents.nodes.faq.embed_query", return_value=mock_vec):
            with patch("app.agents.nodes.faq.get_faq_vectors", return_value=faq_vectors):
                state = dict(_init_state)
                state["original_query"] = "测试查询测" * 3

                def _run():
                    result = asyncio.run(faq_match_node(state))
                    assert isinstance(result, dict)

                benchmark(_run)

    def test_customer_faq_match_100_items(self, benchmark, _init_state):
        from app.agents.customer.faq import customer_faq_match_node

        mock_vec = [0.1] * 1024
        faq_vectors = []
        for i in range(100):
            faq_vectors.append({
                "faq_id": i,
                "question": f"问题{i}",
                "content": f"答案{i}",
                "scope": "public" if i % 2 == 0 else "customer",
                "vector": [0.5] * 1024,
            })

        with patch("app.agents.customer.faq.embed_query", return_value=mock_vec):
            with patch("app.agents.customer.faq.get_faq_vectors", return_value=faq_vectors):
                state = dict(_init_state)
                state["original_query"] = "客户查询测试" * 3

                def _run():
                    result = asyncio.run(customer_faq_match_node(state))
                    assert isinstance(result, dict)

                benchmark(_run)


# ================================================================
# 检索节点延迟基准
# ================================================================
class TestRetrieveNodeLatency:
    @pytest.mark.asyncio
    async def test_retrieve_node_baseline(self, benchmark, _init_state):
        from app.agents.nodes.retrieve import retrieve_node
        from app.retrieval.fusion import FusionResult

        mock_docs = [FusionResult(
            unique_id=f"id_{i}", doc_id=i, chunk_index=0,
            content=f"文档内容片段{i}", fused_score=0.9, scope="public",
        ) for i in range(10)]

        mock_hybrid = AsyncMock(return_value=mock_docs)
        mock_rerank = AsyncMock(return_value=mock_docs[:5])

        with patch("app.agents.nodes.retrieve.hybrid_retrieve", mock_hybrid):
            with patch("app.agents.nodes.retrieve.rerank", mock_rerank):
                with patch("app.agents.nodes.retrieve.get_cache", return_value=None):
                    state = dict(_init_state)
                    state["original_query"] = "检索性能基准测试查询"

                    async def _run():
                        result = await retrieve_node(state)
                        assert result["retrieved_docs"] is not None

                    await benchmark(_run)

    @pytest.mark.asyncio
    async def test_customer_retrieve_node_baseline(self, benchmark, _init_state):
        from app.agents.customer.retrieve import customer_retrieve_node
        from app.retrieval.fusion import FusionResult

        mock_docs = [FusionResult(
            unique_id=f"id_{i}", doc_id=i, chunk_index=0,
            content=f"客服文档{i}", fused_score=0.9, scope="customer",
        ) for i in range(10)]

        mock_hybrid = AsyncMock(return_value=mock_docs)
        mock_rerank = AsyncMock(return_value=mock_docs[:5])

        with patch("app.agents.customer.retrieve.hybrid_retrieve", mock_hybrid):
            with patch("app.agents.customer.retrieve.rerank", mock_rerank):
                state = dict(_init_state)
                state["original_query"] = "客服检索性能测试查询"

                async def _run():
                    result = await customer_retrieve_node(state)
                    assert result["retrieved_docs"] is not None

                await benchmark(_run)


# ================================================================
# 输入校验延迟基准
# ================================================================
class TestInputValidationLatency:
    def test_validate_input_node(self, benchmark, _init_state):
        from app.agents.nodes.validate import validate_input_node
        from app.agents.nodes.validate import update_blocked_patterns

        update_blocked_patterns(["敏感词1", "敏感词2", "禁答", "违禁", "禁止"] * 10)
        state = dict(_init_state)
        state["original_query"] = "这是一个正常的业务查询，关于公司考勤制度的详细说明"

        def _run():
            result = validate_input_node(state)
            assert result["is_blocked"] is False

        benchmark(_run)
        update_blocked_patterns([])

    def test_validate_input_with_blocked_pattern(self, benchmark, _init_state):
        from app.agents.nodes.validate import validate_input_node
        from app.agents.nodes.validate import update_blocked_patterns

        update_blocked_patterns(["禁答词A", "禁答词B"] + ["正常词"] * 100)
        state = dict(_init_state)
        state["original_query"] = "请问禁答词A相关的政策是什么？"

        def _run():
            result = validate_input_node(state)
            assert result["is_blocked"] is True

        benchmark(_run)
        update_blocked_patterns([])


# ================================================================
# 数据库 CRUD 延迟基准
# ================================================================
class TestDatabaseLatency:
    @pytest.mark.asyncio
    async def test_faq_create_in_db(self, benchmark, db_session):
        from app.models.faq import KnowledgeFAQ

        async def _run():
            faq = KnowledgeFAQ(
                category_id=1, question=f"压测FAQ{time.time_ns()}",
                answer="压测答案", scope="public",
            )
            db_session.add(faq)
            await db_session.commit()

        await benchmark(_run)

    @pytest.mark.asyncio
    async def test_faq_query_100_rows(self, benchmark, db_session):
        from app.models.faq import KnowledgeFAQ
        from sqlalchemy import select

        for i in range(100):
            db_session.add(KnowledgeFAQ(
                category_id=1, question=f"FAQ{i}", answer=f"答案{i}", scope="public",
            ))
        await db_session.commit()

        async def _run():
            stmt = select(KnowledgeFAQ).limit(100)
            r = await db_session.execute(stmt)
            _ = r.scalars().all()

        await benchmark(_run)


# ================================================================
# API 吞吐基准 (并发水平)
# ================================================================
class TestAPIThroughput:
    @pytest.mark.asyncio
    async def test_concurrent_chat_requests(self, benchmark, client):
        import asyncio

        mock_graph = MagicMock()
        mock_graph.ainvoke = AsyncMock(return_value={
            "final_answer": "测试回答", "is_blocked": False,
            "confidence": 0.9, "needs_human": False,
            "faq_hit": True, "route": "faq",
            "user_scopes": ["public"],
        })

        with patch("app.api.agent._get_graph", return_value=mock_graph):

            async def _do_request():
                resp = await client.post("/api/agent/internal/chat", json={
                    "message": "并发测试问题", "scope": "public",
                })
                assert resp.status_code == 200

            async def _run():
                tasks = [_do_request() for _ in range(20)]
                await asyncio.gather(*tasks)

            await benchmark(_run)

    @pytest.mark.asyncio
    async def test_concurrent_customer_chat(self, benchmark, client):
        import asyncio

        mock_graph = MagicMock()
        mock_graph.ainvoke = AsyncMock(return_value={
            "final_answer": "客服回答", "is_blocked": False,
            "confidence": 0.85, "needs_human": False,
            "faq_hit": False, "route": "retrieve",
            "user_scopes": ["public", "customer"],
        })

        with patch("app.api.agent._get_customer_graph", return_value=mock_graph):

            async def _do_request():
                resp = await client.post("/api/agent/customer/chat", json={
                    "message": "客服并发测试",
                })
                assert resp.status_code == 200

            async def _run():
                tasks = [_do_request() for _ in range(20)]
                await asyncio.gather(*tasks)

            await benchmark(_run)


# ================================================================
# Graph 构建 + 调用延迟
# ================================================================
class TestGraphLatency:
    def test_build_customer_graph(self, benchmark):
        from app.agents.customer_graph import build_customer_agent_graph

        def _run():
            graph = build_customer_agent_graph()
            assert graph is not None

        benchmark(_run)

    def test_build_internal_graph(self, benchmark):
        from app.agents.graph import build_internal_agent_graph

        def _run():
            graph = build_internal_agent_graph(with_checkpointer=False)
            assert graph is not None

        benchmark(_run)

    @pytest.mark.asyncio
    async def test_graph_invoke_short_circuit(self, benchmark):
        from app.agents.customer_graph import build_customer_agent_graph, create_customer_state

        graph = build_customer_agent_graph()

        mock_fusion = [
            MagicMock(unique_id="1", doc_id=1, chunk_index=0, content="x",
                      fused_score=0.95, scope="customer"),
        ]
        mock_llm = MagicMock()

        async def _stream(msgs):
            yield MagicMock(content="测试回答")
        mock_llm.astream = _stream

        with patch("app.agents.customer.retrieve.hybrid_retrieve", new=AsyncMock(return_value=mock_fusion)):
            with patch("app.agents.customer.retrieve.rerank", new=AsyncMock(return_value=mock_fusion)):
                with patch("app.agents.customer.faq.get_faq_vectors", return_value=[]):
                    with patch("app.agents.customer.faq.embed_query", return_value=[0.1] * 1024):
                        with patch("app.agents.customer.generate.create_llm", return_value=mock_llm):
                            state = create_customer_state(thread_id="bench_graph", query="性能压测查询测试查询")

                            async def _run():
                                result = await graph.ainvoke(state)
                                assert result.get("final_answer") is not None

                            await benchmark(_run)
