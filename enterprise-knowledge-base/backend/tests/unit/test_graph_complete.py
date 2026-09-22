"""LangGraph 完整图 测试 (TDD: RED)"""

import pytest
from unittest.mock import patch


class TestGraphComplete:
    def test_graph_has_11_nodes(self):
        from app.agents.graph import build_internal_agent_graph

        graph = build_internal_agent_graph(with_checkpointer=False)
        nodes = graph.get_graph().nodes
        node_names = {n for n in nodes}
        expected = {
            "validate", "auth", "rewrite", "route", "faq",
            "retrieve", "tools", "context", "generate", "output", "log",
        }
        assert expected.issubset(node_names)

    def test_graph_compiles(self):
        from app.agents.graph import build_internal_agent_graph

        graph = build_internal_agent_graph(with_checkpointer=False)
        assert graph is not None

    @pytest.mark.asyncio
    async def test_graph_sql_blocked(self):
        from app.agents.graph import build_internal_agent_graph
        from app.agents.state import create_initial_state

        graph = build_internal_agent_graph(with_checkpointer=False)
        state = create_initial_state("t_sql2", "DROP TABLE users")
        result = await graph.ainvoke(state)
        assert result["is_blocked"] is True
        assert result["route"] == "reject"

    @pytest.mark.asyncio
    async def test_graph_full_flow(self):
        from app.agents.graph import build_internal_agent_graph
        from app.agents.state import create_initial_state
        from app.retrieval.fusion import FusionResult
        from unittest.mock import AsyncMock, MagicMock

        graph = build_internal_agent_graph(with_checkpointer=False)
        state = create_initial_state("t_full", "考勤制度查询")
        state["user_scopes"] = ["public"]

        mock_docs = [
            FusionResult(unique_id="1_0", doc_id=1, chunk_index=0, content="考勤制度", fused_score=0.9, scope="public"),
        ]

        with patch("app.agents.nodes.retrieve.hybrid_retrieve", new=AsyncMock(return_value=mock_docs)):
            with patch("app.agents.nodes.retrieve.rerank", new=AsyncMock(return_value=mock_docs)):
                mock_llm = MagicMock()

                async def _stream(messages):
                    yield MagicMock(content="根据考勤手册，员工需每日9点打卡。")

                mock_llm.astream = _stream
                mock_tools_llm = MagicMock()
                mock_tools_resp = MagicMock()
                mock_tools_resp.tool_calls = []
                mock_tools_resp.content = ""
                mock_tools_llm.bind_tools.return_value.ainvoke = AsyncMock(return_value=mock_tools_resp)
                with patch("app.agents.nodes.faq.embed_query", new=AsyncMock(return_value=[0.0]*1024)):
                    with patch("app.agents.nodes.generate.create_llm", return_value=mock_llm):
                        with patch("app.agents.nodes.tools.create_llm", return_value=mock_tools_llm):
                            result = await graph.ainvoke(state)
                            assert result is not None
                            assert "route" in result
