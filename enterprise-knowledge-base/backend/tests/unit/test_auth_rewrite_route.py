"""auth_node + rewrite_node + route_node 测试 (TDD: RED)"""

import pytest
from langchain_core.messages import HumanMessage, AIMessage


# ==================== Auth Node ====================

class TestAuthNode:
    @pytest.mark.asyncio
    async def test_map_role_to_scopes_superadmin(self, db_session):
        from app.agents.nodes.auth import map_role_to_scopes

        scopes = await map_role_to_scopes(db_session, "superadmin", "技术部")
        assert "public" in scopes
        assert "internal" in scopes
        assert "customer" in scopes
        assert len(scopes) == 3

    @pytest.mark.asyncio
    async def test_map_role_to_scopes_dept_admin(self, db_session):
        from app.agents.nodes.auth import map_role_to_scopes

        scopes = await map_role_to_scopes(db_session, "dept_admin", "技术部")
        assert "public" in scopes
        assert "internal" in scopes
        assert "customer" not in scopes
        assert len(scopes) == 2

    @pytest.mark.asyncio
    async def test_map_role_to_scopes_readonly(self, db_session):
        from app.agents.nodes.auth import map_role_to_scopes

        scopes = await map_role_to_scopes(db_session, "readonly", "技术部")
        assert scopes == ["public"]

    def test_authenticate_node_sets_scopes(self):
        from app.agents.nodes.auth import authenticate_node
        from app.agents.state import create_initial_state

        state = create_initial_state("t1", "查询", user_id=1, user_role="dept_admin", user_department="研发部")
        result = authenticate_node(state)
        assert "public" in result["user_scopes"]
        assert "internal" in result["user_scopes"]
        assert result["user_role"] == "dept_admin"

    def test_authenticate_preserves_query(self):
        from app.agents.nodes.auth import authenticate_node
        from app.agents.state import create_initial_state

        state = create_initial_state("t2", "考勤查询")
        result = authenticate_node(state)
        assert result["original_query"] == "考勤查询"


# ==================== Rewrite Node ====================

class TestRewriteNode:
    @pytest.mark.asyncio
    async def test_rewrite_with_context(self):
        from unittest.mock import AsyncMock, MagicMock, patch
        from app.agents.nodes.rewrite import rewrite_node
        from app.agents.state import create_initial_state

        mock_llm = MagicMock()
        mock_llm.ainvoke = AsyncMock(return_value=MagicMock(content="OA系统的使用流程是什么"))

        state = create_initial_state("t3", "它的流程是什么")
        state["messages"] = [
            HumanMessage(content="OA系统怎么用"),
            AIMessage(content="OA系统用于办公自动化"),
            HumanMessage(content="它的流程是什么"),
        ]
        with patch("app.agents.nodes.rewrite.create_llm", return_value=mock_llm):
            result = await rewrite_node(state)
        rewritten = result["rewritten_query"]
        assert len(rewritten) > 0

    @pytest.mark.asyncio
    async def test_rewrite_no_history(self):
        from app.agents.nodes.rewrite import rewrite_node
        from app.agents.state import create_initial_state

        state = create_initial_state("t4", "请假流程")
        result = await rewrite_node(state)
        assert result["rewritten_query"] != ""

    @pytest.mark.asyncio
    async def test_rewrite_empty_query(self):
        from app.agents.nodes.rewrite import rewrite_node
        from app.agents.state import create_initial_state

        state = create_initial_state("t5", "")
        result = await rewrite_node(state)
        assert result["rewritten_query"] == ""

    def test_extract_history_last_n(self):
        from app.agents.nodes.rewrite import extract_history

        msgs = [
            HumanMessage(content="q1"),
            AIMessage(content="a1"),
            HumanMessage(content="q2"),
            AIMessage(content="a2"),
            HumanMessage(content="q3"),
            AIMessage(content="a3"),
            HumanMessage(content="q4"),
        ]
        history = extract_history(msgs)
        assert len(history) <= 6


# ==================== Route Node ====================

class TestRouteNode:
    def test_route_blocked(self):
        from app.agents.nodes.route import route_node
        from app.agents.state import create_initial_state

        state = create_initial_state("t6", "DROP TABLE")
        state["is_blocked"] = True
        state["block_reason"] = "sql_injection"
        result = route_node(state)
        assert result["route"] == "reject"

    def test_route_faq_short_query(self):
        from app.agents.nodes.route import route_node
        from app.agents.state import create_initial_state

        state = create_initial_state("t7", "怎么打卡")
        state["user_scopes"] = ["public"]
        result = route_node(state)
        assert result["route"] in ("faq", "retrieve")

    def test_route_retrieve_long_query(self):
        from app.agents.nodes.route import route_node
        from app.agents.state import create_initial_state

        state = create_initial_state("t8", "请详细说明公司的考勤制度和请假流程以及审批步骤")
        state["user_scopes"] = ["public", "internal"]
        result = route_node(state)
        assert result["route"] in ("faq", "retrieve")

    def test_route_no_scopes_rejected(self):
        from app.agents.nodes.route import route_node
        from app.agents.state import create_initial_state

        state = create_initial_state("t9", "查询")
        state["user_scopes"] = []
        result = route_node(state)
        assert result["route"] == "reject"

    def test_route_respects_scope(self):
        from app.agents.nodes.route import route_node
        from app.agents.state import create_initial_state

        state = create_initial_state("t10", "内部数据", user_role="dept_admin")
        state["user_scopes"] = ["public", "internal"]
        result = route_node(state)
        assert result["route"] != "reject"
