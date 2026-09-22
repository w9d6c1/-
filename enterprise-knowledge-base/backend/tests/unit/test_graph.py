"""LangGraph 骨架 测试 (更新 mock)"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


def _make_astream_fn(contents: list[str]):
    async def _stream(messages):
        for c in contents:
            yield MagicMock(content=c)
    return _stream


class TestBuildGraph:
    def test_build_graph_returns_compiled(self):
        from app.agents.graph import build_internal_agent_graph

        graph = build_internal_agent_graph(with_checkpointer=False)
        assert graph is not None

    def test_graph_has_nodes(self):
        from app.agents.graph import build_internal_agent_graph

        graph = build_internal_agent_graph(with_checkpointer=False)
        nodes = graph.get_graph().nodes
        node_names = {n for n in nodes}
        assert "validate" in node_names
        assert "auth" in node_names
        assert "rewrite" in node_names
        assert "route" in node_names
        assert "faq" in node_names

    def test_graph_has_edges(self):
        from app.agents.graph import build_internal_agent_graph

        graph = build_internal_agent_graph(with_checkpointer=False)
        edges = graph.get_graph().edges
        assert len(edges) > 0

    @pytest.mark.asyncio
    async def test_graph_invocation_no_crash(self):
        from app.agents.graph import build_internal_agent_graph
        from app.agents.state import create_initial_state

        graph = build_internal_agent_graph(with_checkpointer=False)
        state = create_initial_state("t_graph", "考勤制度查询")

        mock_docs = []
        with patch("app.agents.nodes.retrieve.hybrid_retrieve", new=AsyncMock(return_value=mock_docs)):
            mock_llm = MagicMock()
            mock_llm.astream = _make_astream_fn(["测试回答"])
            mock_tools_llm = MagicMock()
            mock_tools_response = MagicMock()
            mock_tools_response.tool_calls = []
            mock_tools_response.content = ""
            mock_tools_llm.bind_tools.return_value.ainvoke = AsyncMock(return_value=mock_tools_response)
            with patch("app.agents.nodes.faq.embed_query", new=AsyncMock(return_value=[0.0]*1024)):
                with patch("app.agents.nodes.generate.create_llm", return_value=mock_llm):
                    with patch("app.agents.nodes.tools.create_llm", return_value=mock_tools_llm):
                        result = await graph.ainvoke(state)
                        assert result is not None
                        assert "route" in result

    @pytest.mark.asyncio
    async def test_graph_blocks_sql(self):
        from app.agents.graph import build_internal_agent_graph
        from app.agents.state import create_initial_state

        graph = build_internal_agent_graph(with_checkpointer=False)
        state = create_initial_state("t_sql", "DROP TABLE users")
        result = await graph.ainvoke(state)
        assert result["is_blocked"] is True
        assert result["route"] == "reject"
