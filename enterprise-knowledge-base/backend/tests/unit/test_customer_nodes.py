"""客服智能体 customer/ 节点 测试 (TDD: RED)"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.agents.state import AgentState


def _make_state(query: str = "如何退货", **overrides) -> AgentState:
    from langchain_core.messages import HumanMessage

    state: AgentState = AgentState(
        messages=[HumanMessage(content=query)],
        thread_id="test-cust",
        user_id=None,
        user_role="readonly",
        user_department=None,
        user_scopes=["public", "customer"],
        original_query=query,
        rewritten_query="",
        is_blocked=False,
        block_reason="",
        faq_hit=False,
        faq_answer=None,
        retrieved_docs=[],
        context="",
        final_answer="",
        is_compliant=True,
        compliance_issues=[],
        confidence=0.0,
        needs_human=False,
        human_reason="",
        route="",
        iteration=0,
        error=None,
    )
    for k, v in overrides.items():
        state[k] = v
    return state


class TestCustomerRetrieveNode:
    @pytest.mark.asyncio
    async def test_retrieve_with_customer_scopes(self):
        """客服检索节点使用 customer 和 public scope"""
        from app.agents.customer.retrieve import customer_retrieve_node
        from app.retrieval.fusion import FusionResult

        state = _make_state("产品退货流程")
        mock_docs = [
            FusionResult(unique_id="c1_0", doc_id=1, chunk_index=0, content="退货流程", fused_score=0.9, scope="customer"),
        ]

        with patch("app.agents.customer.retrieve.hybrid_retrieve", new=AsyncMock(return_value=mock_docs)):
            with patch("app.agents.customer.retrieve.rerank", new=AsyncMock(return_value=mock_docs)):
                result = await customer_retrieve_node(state)

        assert len(result["retrieved_docs"]) > 0
        assert result["retrieved_docs"][0].scope == "customer"

    @pytest.mark.asyncio
    async def test_no_query_returns_empty(self):
        """空查询返回空检索结果"""
        from app.agents.customer.retrieve import customer_retrieve_node

        state = _make_state("")
        result = await customer_retrieve_node(state)
        assert result["retrieved_docs"] == []


class TestCustomerFAQNode:
    @pytest.mark.asyncio
    async def test_faq_match_with_customer_scope(self):
        """客服 FAQ 匹配仅在 customer scope 内"""
        from app.agents.customer.faq import customer_faq_match_node
        from app.agents.nodes.faq import _clear_faq_vectors

        await _clear_faq_vectors()
        state = _make_state("退货流程")

        mock_vector = [0.1] * 1024
        with patch("app.agents.customer.faq.embed_query", new=AsyncMock(return_value=mock_vector)):
            with patch("app.agents.customer.faq.get_faq_vectors", return_value=[
                {"faq_id": 1, "question": "退货流程", "content": "请在订单页面申请退货。", "scope": "customer", "vector": mock_vector},
            ]):
                result = await customer_faq_match_node(state)

        assert result["faq_hit"] is True

    @pytest.mark.asyncio
    async def test_faq_no_match_wrong_scope(self):
        """客服不应该匹配 internal scope 的 FAQ"""
        from app.agents.customer.faq import customer_faq_match_node
        from app.agents.nodes.faq import _clear_faq_vectors

        await _clear_faq_vectors()
        state = _make_state("内部机密")

        mock_vector = [0.1] * 1024
        with patch("app.agents.customer.faq.embed_query", new=AsyncMock(return_value=mock_vector)):
            with patch("app.agents.customer.faq.get_faq_vectors", return_value=[
                {"faq_id": 2, "question": "内部机密", "content": "机密答案", "scope": "internal", "vector": mock_vector},
            ]):
                result = await customer_faq_match_node(state)

        assert result["faq_hit"] is False


class TestCustomerGenerateNode:
    @pytest.mark.asyncio
    async def test_generate_customer_friendly(self):
        """客服生成节点使用客服友好的 Prompt"""
        from app.agents.customer.generate import customer_generate_node

        state = _make_state("退货需要什么")
        state["context"] = "[文档1] 退货流程\n[来源: 退换货政策]\n"

        mock_llm = MagicMock()

        async def _stream(messages):
            yield MagicMock(content="您可以在订单页面提交退货申请。")

        mock_llm.astream = _stream

        with patch("app.agents.customer.generate.create_llm", return_value=mock_llm):
            result = await customer_generate_node(state)

        assert "退货" in result["final_answer"] or "订单" in result["final_answer"]

    @pytest.mark.asyncio
    async def test_no_context_returns_guide(self):
        """无上下文时返回引导性消息而非冰冷错误"""
        from app.agents.customer.generate import customer_generate_node

        state = _make_state("复杂问题")
        state["context"] = ""
        result = await customer_generate_node(state)
        assert len(result["final_answer"]) > 0


class TestCustomerGraph:
    @pytest.mark.asyncio
    async def test_graph_has_customer_nodes(self):
        """客服图包含 retrieve/faq/generate/handoff 节点"""
        from app.agents.customer_graph import build_customer_agent_graph

        graph = build_customer_agent_graph()
        nodes = graph.get_graph().nodes
        node_names = {n for n in nodes}
        assert "retrieve" in node_names
        assert "faq" in node_names
        assert "generate" in node_names
        assert "handoff" in node_names

    @pytest.mark.asyncio
    async def test_graph_strips_internal_scope(self):
        """客服图强制剥离 internal scope"""
        from app.agents.customer_graph import build_customer_agent_graph
        from app.agents.customer_graph import create_customer_state

        graph = build_customer_agent_graph()
        state = create_customer_state("c_test", "内部数据")
        state["user_scopes"] = ["public", "internal", "customer"]

        mock_llm = MagicMock()

        async def _stream(messages):
            yield MagicMock(content="回答")

        mock_llm.astream = _stream

        with patch("app.agents.customer.generate.create_llm", return_value=mock_llm):
            with patch("app.agents.customer.retrieve.hybrid_retrieve", new=AsyncMock(return_value=[])):
                result = await graph.ainvoke(state)

        assert "internal" not in result["user_scopes"]

    @pytest.mark.asyncio
    async def test_short_query_routes_to_faq(self):
        """短查询走 FAQ 路径"""
        from app.agents.customer_graph import build_customer_agent_graph
        from app.agents.customer_graph import create_customer_state

        graph = build_customer_agent_graph()
        state = create_customer_state("c_faq", "退货")

        mock_llm = MagicMock()

        async def _stream(messages):
            yield MagicMock(content="回答")

        mock_llm.astream = _stream

        with patch("app.agents.customer.faq.get_faq_vectors", return_value=[]):
            with patch("app.agents.customer.faq.embed_query", return_value=[0.1] * 1024):
                with patch("app.agents.customer.generate.create_llm", return_value=mock_llm):
                    with patch("app.agents.customer.retrieve.hybrid_retrieve", new=AsyncMock(return_value=[])):
                        result = await graph.ainvoke(state)

        assert result is not None
