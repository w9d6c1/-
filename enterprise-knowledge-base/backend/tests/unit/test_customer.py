"""客服智能体 测试 (TDD: RED)"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


class TestCustomerAgentState:
    def test_create_customer_state(self):
        from app.agents.customer_graph import create_customer_state

        state = create_customer_state(thread_id="c1", query="如何退货")
        assert state["thread_id"] == "c1"
        assert state["original_query"] == "如何退货"
        assert state["user_scopes"] == ["public", "customer"]
        assert state["needs_human"] is False
        assert state["confidence"] == 0.0

    def test_customer_state_scopes_restricted(self):
        from app.agents.customer_graph import create_customer_state

        state = create_customer_state(thread_id="c2", query="内部机密")
        assert "internal" not in state["user_scopes"]


class TestCustomerRouteNode:
    def test_customer_route_restricts_scope(self):
        from app.agents.customer_graph import customer_route_node
        from app.agents.customer_graph import create_customer_state

        state = create_customer_state("c3", "产品价格")
        state["user_scopes"] = ["public", "internal", "customer"]
        result = customer_route_node(state)
        assert "internal" not in result["user_scopes"]

    def test_customer_route_short_query_to_faq(self):
        from app.agents.customer_graph import customer_route_node
        from app.agents.customer_graph import create_customer_state

        state = create_customer_state("c4", "退货")
        result = customer_route_node(state)
        assert result["route"] in ("faq", "retrieve")


class TestHumanHandoffNode:
    def test_handoff_low_confidence(self):
        from app.agents.customer_graph import human_handoff_node
        from app.agents.customer_graph import create_customer_state

        state = create_customer_state("c5", "复杂问题")
        state["confidence"] = 0.3
        result = human_handoff_node(state)
        assert result["needs_human"] is True

    def test_handoff_user_request(self):
        from app.agents.customer_graph import human_handoff_node
        from app.agents.customer_graph import create_customer_state

        state = create_customer_state("c6", "我要转人工客服")
        result = human_handoff_node(state)
        assert result["needs_human"] is True

    def test_handoff_sensitive_topic(self):
        from app.agents.customer_graph import human_handoff_node
        from app.agents.customer_graph import create_customer_state

        state = create_customer_state("c7", "投诉")
        state["confidence"] = 0.8
        result = human_handoff_node(state)
        assert result["needs_human"] is True

    def test_handoff_no_trigger(self):
        from app.agents.customer_graph import human_handoff_node
        from app.agents.customer_graph import create_customer_state

        state = create_customer_state("c8", "产品使用说明")
        state["confidence"] = 0.85
        result = human_handoff_node(state)
        assert result["needs_human"] is False


class TestCustomerGraph:
    def test_customer_graph_builds(self):
        from app.agents.customer_graph import build_customer_agent_graph

        graph = build_customer_agent_graph()
        assert graph is not None

    def test_customer_graph_has_nodes(self):
        from app.agents.customer_graph import build_customer_agent_graph

        graph = build_customer_agent_graph()
        nodes = graph.get_graph().nodes
        node_names = {n for n in nodes}
        assert "route" in node_names
        assert "handoff" in node_names
        assert "generate" in node_names

    @pytest.mark.asyncio
    async def test_customer_graph_blocks_internal_scope(self):
        from app.agents.customer_graph import build_customer_agent_graph
        from app.agents.customer_graph import create_customer_state

        graph = build_customer_agent_graph()
        state = create_customer_state("c9", "内部数据")
        state["user_scopes"] = ["public", "internal", "customer"]

        mock_llm = MagicMock()

        async def _stream(messages):
            yield MagicMock(content="回答")

        mock_llm.astream = _stream

        with patch("app.agents.customer.generate.create_llm", return_value=mock_llm):
            with patch("app.agents.customer.retrieve.hybrid_retrieve", new=AsyncMock(return_value=[])):
                result = await graph.ainvoke(state)

        assert "internal" not in result["user_scopes"]
