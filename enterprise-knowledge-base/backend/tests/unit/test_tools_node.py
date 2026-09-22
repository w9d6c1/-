"""Tools 节点 — ReAct 工具调用循环 测试 (TDD: RED)"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.agents.state import AgentState


def _make_state(query: str = "如何使用考勤系统", **overrides) -> AgentState:
    from langchain_core.messages import HumanMessage

    state: AgentState = AgentState(
        messages=[HumanMessage(content=query)],
        thread_id="test-tools",
        user_id=None,
        user_role="readonly",
        user_department=None,
        user_scopes=["public"],
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
        route="retrieve",
        iteration=0,
        error=None,
    )
    for k, v in overrides.items():
        state[k] = v
    return state


class TestToolDefinitions:
    def test_tools_are_callable(self):
        from app.agents.nodes.tools import TOOLS

        assert len(TOOLS) >= 2
        for tool in TOOLS:
            assert hasattr(tool, "name")
            assert hasattr(tool, "description")

    def test_tool_names(self):
        from app.agents.nodes.tools import TOOLS

        names = {t.name for t in TOOLS}
        assert "search_knowledge_base" in names
        assert "decompose_query" in names


class TestToolDecisionNode:
    @pytest.mark.asyncio
    async def test_wecom_channel_with_docs_skips_llm(self):
        """企微渠道且已有检索结果时跳过 ReAct 循环，不调用 LLM（性能优化）"""
        from app.agents.nodes.tools import tool_decision_node
        from app.retrieval.fusion import FusionResult

        state = _make_state("考勤制度")
        state["channel"] = "wecom"
        state["retrieved_docs"] = [
            FusionResult(unique_id="1_0", doc_id=1, chunk_index=0, content="考勤内容", fused_score=0.9, scope="public"),
        ]

        mock_llm = MagicMock()
        with patch("app.agents.nodes.tools.create_llm", return_value=mock_llm):
            result = await tool_decision_node(state)

        mock_llm.bind_tools.assert_not_called()
        assert result["iteration"] >= 1

    @pytest.mark.asyncio
    async def test_wecom_channel_without_docs_still_searches(self):
        """企微渠道但无检索结果时仍走 ReAct 循环，保留补充检索能力"""
        from app.agents.nodes.tools import tool_decision_node

        state = _make_state("考勤制度")
        state["channel"] = "wecom"
        state["retrieved_docs"] = []

        mock_llm = MagicMock()
        mock_response = MagicMock()
        mock_response.tool_calls = []
        mock_response.content = "无需额外工具"
        mock_llm.bind_tools.return_value.ainvoke = AsyncMock(return_value=mock_response)

        with patch("app.agents.nodes.tools.create_llm", return_value=mock_llm):
            result = await tool_decision_node(state)

        mock_llm.bind_tools.assert_called()
        assert result["iteration"] > 0

    @pytest.mark.asyncio
    async def test_no_retrieved_docs_no_tool_calls(self):
        """无检索文档时 LLM 决定不需要工具 → 直接返回"""
        from app.agents.nodes.tools import tool_decision_node

        state = _make_state("考勤制度")
        mock_llm = MagicMock()
        mock_response = MagicMock()
        mock_response.tool_calls = []
        mock_response.content = "无需额外工具"
        mock_llm.bind_tools.return_value.ainvoke = AsyncMock(return_value=mock_response)

        with patch("app.agents.nodes.tools.create_llm", return_value=mock_llm):
            result = await tool_decision_node(state)

        assert result["iteration"] > 0  # at least 1 iteration consumed
        assert mock_llm.bind_tools.called

    @pytest.mark.asyncio
    async def test_increments_iteration(self):
        """每次进入节点都递增迭代计数"""
        from app.agents.nodes.tools import tool_decision_node

        state = _make_state("考勤制度", iteration=0)

        mock_llm = MagicMock()
        mock_response = MagicMock()
        mock_response.tool_calls = []
        mock_response.content = "ok"
        mock_llm.bind_tools.return_value.ainvoke = AsyncMock(return_value=mock_response)

        with patch("app.agents.nodes.tools.create_llm", return_value=mock_llm):
            result = await tool_decision_node(state)

        assert result["iteration"] >= 1

    @pytest.mark.asyncio
    async def test_max_iteration_limit(self):
        """达到最大迭代次数时不再调用 LLM"""
        from app.agents.nodes.tools import tool_decision_node

        state = _make_state("考勤制度", iteration=3)

        mock_llm = MagicMock()

        with patch("app.agents.nodes.tools.create_llm", return_value=mock_llm):
            result = await tool_decision_node(state)

        # LLM 不应被调用
        mock_llm.bind_tools.assert_not_called()
        mock_llm.ainvoke.assert_not_called()

    @pytest.mark.asyncio
    async def test_tool_call_search_knowledge_base(self):
        """LLM 请求 search_knowledge_base 工具 → 执行工具并更新检索文档"""
        from app.agents.nodes.tools import tool_decision_node
        from app.retrieval.fusion import FusionResult

        state = _make_state("如何申请报销")
        state["retrieved_docs"] = [
            FusionResult(unique_id="1_0", doc_id=1, chunk_index=0, content="报销流程", fused_score=0.7, scope="public"),
        ]

        mock_llm = MagicMock()
        # First call: LLM requests tool
        response1 = MagicMock()
        response1.tool_calls = [
            {"name": "search_knowledge_base", "args": {"query": "报销审批流程"}, "id": "call_1"}
        ]
        response1.content = ""
        # Second call: LLM done
        response2 = MagicMock()
        response2.tool_calls = []
        response2.content = "搜索完成"
        bound_ainvoke = AsyncMock(side_effect=[response1, response2])
        mock_llm.bind_tools.return_value.ainvoke = bound_ainvoke

        mock_docs = [
            FusionResult(unique_id="2_0", doc_id=2, chunk_index=0, content="报销审批流程", fused_score=0.9, scope="public"),
        ]

        with patch("app.agents.nodes.tools.create_llm", return_value=mock_llm):
            with patch("app.agents.nodes.tools._execute_tool", new=AsyncMock()) as mock_exec:
                async def execute_side_effect(tool_call, state_in):
                    return mock_docs

                mock_exec.side_effect = execute_side_effect

                result = await tool_decision_node(state)

        assert bound_ainvoke.call_count >= 2
        assert result["iteration"] >= 1
        assert any(d.doc_id == 2 for d in result["retrieved_docs"])

    @pytest.mark.asyncio
    async def test_tool_loop_max_three_iterations(self):
        """工具调用循环最多 3 次"""
        from app.agents.nodes.tools import tool_decision_node
        from app.retrieval.fusion import FusionResult

        state = _make_state("复杂查询", iteration=0)
        state["retrieved_docs"] = [
            FusionResult(unique_id="1_0", doc_id=1, chunk_index=0, content="内容", fused_score=0.5, scope="public"),
        ]

        mock_llm = MagicMock()
        # Each call produces a tool call (stubborn LLM)
        response = MagicMock()
        response.tool_calls = [
            {"name": "search_knowledge_base", "args": {"query": "more info"}, "id": "call_x"}
        ]
        response.content = ""
        mock_llm.bind_tools.return_value.ainvoke = AsyncMock(return_value=response)

        with patch("app.agents.nodes.tools.create_llm", return_value=mock_llm):
            with patch("app.agents.nodes.tools._execute_tool", new=AsyncMock(return_value=[])):
                result = await tool_decision_node(state)

        # 循环上限: iteration 从 0 开始，最多 3 次工具调用
        assert result["iteration"] <= 3

    @pytest.mark.asyncio
    async def test_decompose_query_tool(self):
        """LLM 请求分解查询 → 将复杂查询拆为子查询"""
        from app.agents.nodes.tools import tool_decision_node
        from app.retrieval.fusion import FusionResult

        state = _make_state("报销流程和考勤制度有什么不同，新员工如何申请")
        state["retrieved_docs"] = [
            FusionResult(unique_id="1_0", doc_id=1, chunk_index=0, content="部分信息", fused_score=0.6, scope="public"),
        ]

        mock_llm = MagicMock()
        response1 = MagicMock()
        response1.tool_calls = [
            {"name": "decompose_query", "args": {"query": state["original_query"]}, "id": "call_decompose"}
        ]
        response1.content = ""
        response2 = MagicMock()
        response2.tool_calls = []
        response2.content = "done"
        mock_llm.bind_tools.return_value.ainvoke = AsyncMock(side_effect=[response1, response2])

        with patch("app.agents.nodes.tools.create_llm", return_value=mock_llm):
            with patch("app.agents.nodes.tools._execute_tool", new=AsyncMock()) as mock_exec:
                async def execute_side_effect(tool_call, state_in):
                    from app.retrieval.fusion import FusionResult as FR
                    return [FR(unique_id="99_0", doc_id=99, chunk_index=0, content="子查询结果", fused_score=0.8, scope="public")]

                mock_exec.side_effect = execute_side_effect

                result = await tool_decision_node(state)

        assert result["iteration"] >= 1

    @pytest.mark.asyncio
    async def test_preserves_original_docs(self):
        """工具节点不应丢失原始检索文档"""
        from app.agents.nodes.tools import tool_decision_node
        from app.retrieval.fusion import FusionResult

        original_docs = [
            FusionResult(unique_id="1_0", doc_id=1, chunk_index=0, content="原始内容", fused_score=0.9, scope="public"),
        ]
        state = _make_state("查询", retrieved_docs=original_docs)

        mock_llm = MagicMock()
        mock_response = MagicMock()
        mock_response.tool_calls = []
        mock_response.content = "done"
        mock_llm.bind_tools.return_value.ainvoke = AsyncMock(return_value=mock_response)

        with patch("app.agents.nodes.tools.create_llm", return_value=mock_llm):
            result = await tool_decision_node(state)

        doc_ids = {d.unique_id for d in result["retrieved_docs"]}
        assert "1_0" in doc_ids
