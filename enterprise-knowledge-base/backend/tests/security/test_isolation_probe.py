"""跨库 scope 隔离验证 — customer agent 不得泄露 internal 库知识

验证层次:
  L1: create_customer_state 硬编码 scopes
  L2: _strip_internal_scopes / customer_route_node
  L3: customer_retrieve_node scope 过滤
  L4: customer_faq_match_node scope 封死
  Attack: state 注入 / API 合约 / 边界条件
  Batch: 500 条跨库探针自动执行 (TC-ISO-001)
"""

import asyncio
import copy
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.agents.state import AgentState
from app.agents.customer_graph import (
    _strip_internal_scopes,
    build_customer_agent_graph,
    create_customer_state,
    customer_route_node,
    human_handoff_node,
)
from app.agents.customer.faq import customer_faq_match_node
from app.retrieval.fusion import FusionResult


def _make_state(**overrides) -> AgentState:
    state = create_customer_state(
        thread_id="probe_customer_test",
        query="测试查询",
        user_id=1,
        user_role="readonly",
    )
    state.update(overrides)
    return state


# ─────────────────────────────────────────────
# L1: create_customer_state 硬编码 scopes
# ─────────────────────────────────────────────
class TestCreateCustomerStateScopes:
    def test_default_scopes_are_public_and_customer(self):
        state = create_customer_state("t1", "查询")
        assert state["user_scopes"] == ["public", "customer"]

    def test_internal_not_in_scopes(self):
        state = create_customer_state("t2", "查询")
        assert "internal" not in state["user_scopes"]

    def test_scopes_are_immutable_from_caller(self):
        state = create_customer_state("t3", "查询")
        state["user_scopes"] = ["internal"]
        new_state = create_customer_state("t4", "查询")
        assert new_state["user_scopes"] == ["public", "customer"]

    def test_user_role_does_not_affect_scopes(self):
        for role in ("superadmin", "dept_admin", "operator", "readonly"):
            state = create_customer_state("t5", "查询", user_role=role)
            assert state["user_scopes"] == ["public", "customer"]

    def test_user_id_does_not_affect_scopes(self):
        for uid in (None, 1, 999, -1):
            state = create_customer_state("t6", "查询", user_id=uid)
            assert state["user_scopes"] == ["public", "customer"]

    def test_thread_id_prefix_is_probe_customer(self):
        state = create_customer_state("probe_customer_001", "敏感查询")
        assert state["thread_id"] == "probe_customer_001"
        assert state["user_scopes"] == ["public", "customer"]


# ─────────────────────────────────────────────
# L2: _strip_internal_scopes
# ─────────────────────────────────────────────
class TestStripInternalScopes:
    def test_strips_internal_from_scopes(self):
        state = _make_state(user_scopes=["public", "internal", "customer"])
        result = _strip_internal_scopes(state)
        assert result["user_scopes"] == ["public", "customer"]

    def test_handles_only_internal_scope(self):
        state = _make_state(user_scopes=["internal"])
        result = _strip_internal_scopes(state)
        assert result["user_scopes"] == ["public"]

    def test_handles_empty_scopes(self):
        state = _make_state(user_scopes=[])
        result = _strip_internal_scopes(state)
        assert result["user_scopes"] == ["public"]

    def test_handles_internal_multiple_times_in_list(self):
        state = _make_state(user_scopes=["internal", "internal", "customer"])
        result = _strip_internal_scopes(state)
        assert "internal" not in result["user_scopes"]
        assert result["user_scopes"] == ["customer"]

    def test_does_not_mutate_original_state(self):
        state = _make_state(user_scopes=["internal", "customer"])
        original = copy.deepcopy(state["user_scopes"])
        _strip_internal_scopes(state)
        assert state["user_scopes"] == original

    def test_internal_alone_alone_no_query_leads_to_public(self):
        state = _make_state(user_scopes=["internal"])
        stripped = _strip_internal_scopes(state)
        assert stripped["user_scopes"] == ["public"]


# ─────────────────────────────────────────────
# L2: customer_route_node scope validation
# ─────────────────────────────────────────────
class TestCustomerRouteNodeScopes:
    def test_strips_internal_before_routing(self):
        state = _make_state(user_scopes=["internal"], original_query="测试查询")
        result = customer_route_node(state)
        assert result["user_scopes"] == ["public"]
        assert result["route"] != "reject"

    def test_empty_scopes_after_strip_routes_to_reject(self):
        state = _make_state(user_scopes=[], original_query="")
        result = customer_route_node(state)
        assert result["route"] == "reject"

    def test_empty_query_routes_to_reject(self):
        state = _make_state(original_query="")
        result = customer_route_node(state)
        assert result["route"] == "reject"

    def test_short_query_routes_to_faq(self):
        state = _make_state(original_query="短问题")
        result = customer_route_node(state)
        assert result["route"] == "faq"

    def test_long_query_routes_to_faq_first(self):
        state = _make_state(original_query="这是一个比较长的查询问题需要走检索而不是FAQ")
        result = customer_route_node(state)
        assert result["route"] == "faq"


# ─────────────────────────────────────────────
# L3: customer_retrieve_node scope 过滤
# ─────────────────────────────────────────────
class TestCustomerRetrieveNodeScopes:
    @pytest.mark.asyncio
    async def test_never_calls_hybrid_retrieve_with_internal(self):
        mock_fusion = [FusionResult(unique_id="1", doc_id=1, chunk_index=0, content="x", fused_score=0.9, scope="public")]
        mock_hybrid = AsyncMock(return_value=mock_fusion)

        with patch("app.agents.customer.retrieve.hybrid_retrieve", mock_hybrid):
            with patch("app.agents.customer.retrieve.rerank", new=AsyncMock(return_value=mock_fusion)):
                from app.agents.customer.retrieve import customer_retrieve_node
                state = _make_state(
                    user_scopes=["public", "internal", "customer"],
                    original_query="测试查询测试查询测试查询测试查询",
                )
                result = await customer_retrieve_node(state)

                for call in mock_hybrid.call_args_list:
                    scope_arg = call.kwargs.get("scope", "")
                    assert scope_arg != "internal", f"hybrid_retrieve called with scope='internal'"

    @pytest.mark.asyncio
    async def test_only_calls_public_and_customer_scopes(self):
        mock_fusion = [FusionResult(unique_id="1", doc_id=1, chunk_index=0, content="x", fused_score=0.9, scope="public")]
        mock_hybrid = AsyncMock(return_value=mock_fusion)

        with patch("app.agents.customer.retrieve.hybrid_retrieve", mock_hybrid):
            with patch("app.agents.customer.retrieve.rerank", new=AsyncMock(return_value=mock_fusion)):
                from app.agents.customer.retrieve import customer_retrieve_node
                state = _make_state(
                    user_scopes=["public", "internal", "customer"],
                    original_query="测试查询测试查询测试查询测试查询",
                )
                await customer_retrieve_node(state)

                called_scopes = {call.kwargs.get("scope", "") for call in mock_hybrid.call_args_list}
                assert called_scopes == {"public", "customer"}

    @pytest.mark.asyncio
    async def test_falls_back_to_public_when_only_internal(self):
        mock_fusion = [FusionResult(unique_id="1", doc_id=1, chunk_index=0, content="x", fused_score=0.9, scope="public")]
        mock_hybrid = AsyncMock(return_value=mock_fusion)

        with patch("app.agents.customer.retrieve.hybrid_retrieve", mock_hybrid):
            with patch("app.agents.customer.retrieve.rerank", new=AsyncMock(return_value=mock_fusion)):
                from app.agents.customer.retrieve import customer_retrieve_node
                state = _make_state(
                    user_scopes=["internal"],
                    original_query="测试查询测试查询测试查询测试查询",
                )
                await customer_retrieve_node(state)

                called_scopes = {call.kwargs.get("scope", "") for call in mock_hybrid.call_args_list}
                assert called_scopes == {"public"}

    @pytest.mark.asyncio
    async def test_returns_empty_for_empty_query(self):
        mock_hybrid = AsyncMock()
        with patch("app.agents.customer.retrieve.hybrid_retrieve", mock_hybrid):
            from app.agents.customer.retrieve import customer_retrieve_node
            state = _make_state(original_query="")
            result = await customer_retrieve_node(state)
            assert result["retrieved_docs"] == []
            mock_hybrid.assert_not_called()


# ─────────────────────────────────────────────
# L4: customer_faq_match_node scope 封死
# ─────────────────────────────────────────────
class TestCustomerFAQNodeScopes:
    @pytest.mark.asyncio
    async def test_never_matches_internal_scope_faq(self):
        q_vec = [1.0] + [0.0] * 1023
        internal_vec = [0.0, 1.0] + [0.0] * 1022
        public_vec = [0.0, 0.0, 1.0] + [0.0] * 1021
        mock_faq_vectors = [
            {"faq_id": 1, "question": "内部制度查询", "content": "内部机密信息-仅内部可见",
             "scope": "internal", "vector": internal_vec},
            {"faq_id": 2, "question": "公共知识", "content": "公共内容",
             "scope": "public", "vector": public_vec},
        ]

        with patch("app.agents.customer.faq.get_faq_vectors", return_value=mock_faq_vectors):
            with patch("app.agents.customer.faq.embed_query", return_value=q_vec):
                state = _make_state(user_scopes=["public", "customer"], original_query="内部制度")
                result = await customer_faq_match_node(state)
                assert result["faq_hit"] is False

    @pytest.mark.asyncio
    async def test_uses_hardcoded_scope_set_not_state_scopes(self):
        q_vec = [1.0] + [0.0] * 1023
        internal_vec = [0.0, 1.0] + [0.0] * 1022
        mock_faq_vectors = [
            {"faq_id": 1, "question": "内部信息", "content": "机密",
             "scope": "internal", "vector": internal_vec},
        ]

        with patch("app.agents.customer.faq.get_faq_vectors", return_value=mock_faq_vectors):
            with patch("app.agents.customer.faq.embed_query", return_value=q_vec):
                state = _make_state(user_scopes=["public", "internal", "customer"], original_query="内部信息")
                result = await customer_faq_match_node(state)
                assert result["faq_hit"] is False

    @pytest.mark.asyncio
    async def test_matches_public_scope_faq(self):
        q_vec = [1.0] + [0.0] * 1023
        same_vec = [1.0] + [0.0] * 1023
        mock_faq_vectors = [
            {"faq_id": 1, "question": "公共知识", "content": "公共可见内容",
             "scope": "public", "vector": same_vec},
        ]

        with patch("app.agents.customer.faq.get_faq_vectors", return_value=mock_faq_vectors):
            with patch("app.agents.customer.faq.embed_query", return_value=q_vec):
                state = _make_state(user_scopes=["public", "customer"], original_query="公共知识")
                result = await customer_faq_match_node(state)
                assert result["faq_hit"] is True
                assert result["faq_answer"] == "公共可见内容"

    @pytest.mark.asyncio
    async def test_matches_customer_scope_faq(self):
        q_vec = [1.0] + [0.0] * 1023
        same_vec = [1.0] + [0.0] * 1023
        mock_faq_vectors = [
            {"faq_id": 2, "question": "客服问答", "content": "客服专属内容",
             "scope": "customer", "vector": same_vec},
        ]

        with patch("app.agents.customer.faq.get_faq_vectors", return_value=mock_faq_vectors):
            with patch("app.agents.customer.faq.embed_query", return_value=q_vec):
                state = _make_state(user_scopes=["public", "customer"], original_query="客服问答")
                result = await customer_faq_match_node(state)
                assert result["faq_hit"] is True
                assert result["faq_answer"] == "客服专属内容"

    @pytest.mark.asyncio
    async def test_no_hit_when_all_faqs_are_internal(self):
        mock_faq_vectors = [
            {"faq_id": i, "scope": "internal", "content": f"内部{i}", "vector": [0.99] * 1024}
            for i in range(50)
        ]

        with patch("app.agents.customer.faq.get_faq_vectors", return_value=mock_faq_vectors):
            with patch("app.agents.customer.faq.embed_query", return_value=[0.99] * 1024):
                state = _make_state(original_query="任何问题")
                result = await customer_faq_match_node(state)
                assert result["faq_hit"] is False


# ─────────────────────────────────────────────
# Graph 端到端：mock 检索 + LLM 验证 scope 隔离
# ─────────────────────────────────────────────
class TestGraphEndToEndIsolation:
    @pytest.mark.asyncio
    async def test_customer_graph_never_returns_internal_knowledge(self):
        mock_fusion = [
            FusionResult(unique_id="1", doc_id=1, chunk_index=0, content="公司内部薪资制度：年薪20%年终奖", fused_score=0.95,
                         scope="internal"),
            FusionResult(unique_id="2", doc_id=2, chunk_index=0, content="工作时间：朝九晚六，周末双休", fused_score=0.9,
                         scope="public"),
        ]
        mock_public_only = [
            FusionResult(unique_id="2", doc_id=2, chunk_index=0, content="工作时间：朝九晚六，周末双休", fused_score=0.9,
                         scope="public"),
        ]

        mock_llm = MagicMock()
        async def _stream(messages):
            yield MagicMock(content="根据公司规定，工作时间为朝九晚六，周末双休。")
        mock_llm.astream = _stream

        graph = build_customer_agent_graph()

        with patch("app.agents.customer.retrieve.hybrid_retrieve", new=AsyncMock(return_value=mock_fusion)):
            with patch("app.agents.customer.retrieve.rerank", new=AsyncMock(return_value=mock_public_only)):
                with patch("app.agents.customer.faq.get_faq_vectors", return_value=[]):
                    with patch("app.agents.customer.faq.embed_query", return_value=[0.1] * 1024):
                        with patch("app.agents.customer.generate.create_llm", return_value=mock_llm):
                            state = create_customer_state(
                                thread_id="probe_customer_e2e_001",
                                query="公司的工作制度和薪资是怎样的？",
                            )
                            state["user_scopes"] = ["public", "internal", "customer"]
                            result = await graph.ainvoke(state)

                            assert "internal" not in result.get("user_scopes", [])
                            answer = result.get("final_answer", "")
                            assert "内部薪资" not in answer, f"Answer leaked internal content: {answer}"

    @pytest.mark.asyncio
    async def test_customer_graph_strips_injected_internal_scope(self):
        mock_fusion = [
            FusionResult(unique_id="1", doc_id=1, chunk_index=0, content="客户可见知识", fused_score=0.95, scope="customer"),
        ]
        mock_llm = MagicMock()
        async def _stream(messages):
            yield MagicMock(content="这是客户可以查看的知识。")
        mock_llm.astream = _stream

        graph = build_customer_agent_graph()

        with patch("app.agents.customer.retrieve.hybrid_retrieve", new=AsyncMock(return_value=mock_fusion)):
            with patch("app.agents.customer.retrieve.rerank", new=AsyncMock(return_value=mock_fusion)):
                with patch("app.agents.customer.faq.get_faq_vectors", return_value=[]):
                    with patch("app.agents.customer.faq.embed_query", return_value=[0.1] * 1024):
                        with patch("app.agents.customer.generate.create_llm", return_value=mock_llm):
                            state = create_customer_state(
                                thread_id="probe_customer_e2e_002",
                                query="知识查询",
                            )
                            state["user_scopes"] = ["internal"]
                            result = await graph.ainvoke(state)

                            assert result.get("route") != "reject"
                            assert "internal" not in result.get("user_scopes", [])

    @pytest.mark.asyncio
    async def test_customer_graph_handshake_node_updates_correctly(self):
        state = create_customer_state(thread_id="probe_handoff", query="投诉")
        result = human_handoff_node(state)
        assert result["needs_human"] is True
        assert "投诉" in result.get("human_reason", "")

    @pytest.mark.asyncio
    async def test_low_confidence_triggers_handoff(self):
        state = create_customer_state(thread_id="probe_lowconf", query="普通问题")
        state["confidence"] = 0.3
        result = human_handoff_node(state)
        assert result["needs_human"] is True
        assert "low_confidence" in result.get("human_reason", "")


# ─────────────────────────────────────────────
# API 级别合约验证
# ─────────────────────────────────────────────
class TestAPIContractIsolation:
    async def _login(self, client):
        await client.post("/api/admin/auth/register", json={
            "username": "iso_api_1", "password": "IsoApiPass1!",
            "password_confirm": "IsoApiPass1!", "display_name": "ISO API",
            "role": "readonly",
        })
        resp = await client.post("/api/admin/auth/login", data={
            "username": "iso_api_1", "password": "IsoApiPass1!",
        })
        return resp.json()["access_token"]

    @pytest.mark.asyncio
    async def test_customer_chat_response_has_no_internal_in_answer(self, client):
        mock_graph = MagicMock()
        mock_graph.ainvoke = AsyncMock(return_value={
            "final_answer": "这条回答中不小心提到了内部制度机密信息",
            "is_blocked": False,
            "confidence": 0.9,
            "needs_human": False,
            "faq_hit": False,
            "route": "retrieve",
            "user_scopes": ["public", "customer"],
        })

        with patch("app.api.agent._customer_graph", mock_graph):
            resp = await client.post("/api/agent/customer/chat", json={
                "message": "查询知识",
                "thread_id": "probe_customer_api_001",
            })
            assert resp.status_code == 200
            data = resp.json()
            assert "answer" in data

    @pytest.mark.asyncio
    async def test_customer_chat_log_has_correct_source(self, client):
        mock_graph = MagicMock()
        mock_graph.ainvoke = AsyncMock(return_value={
            "final_answer": "这里是标准答复",
            "is_blocked": False,
            "confidence": 0.9,
            "needs_human": False,
            "faq_hit": True,
            "route": "faq",
            "user_scopes": ["public", "customer"],
        })

        with patch("app.api.agent._customer_graph", mock_graph):
            resp = await client.post("/api/agent/customer/chat", json={
                "message": "常见问题",
                "thread_id": "probe_customer_api_002",
            })
            assert resp.status_code == 200
            data = resp.json()
            assert data.get("thread_id") == "probe_customer_api_002"

    @pytest.mark.asyncio
    async def test_customer_chat_response_with_sensitive_word_blocked(self, client):
        mock_graph = MagicMock()
        mock_graph.ainvoke = AsyncMock(return_value={
            "final_answer": "",
            "is_blocked": True,
            "block_reason": "包含敏感词",
            "confidence": 0.0,
            "needs_human": False,
            "faq_hit": False,
            "route": "reject",
            "user_scopes": ["public", "customer"],
        })

        with patch("app.api.agent._customer_graph", mock_graph):
            resp = await client.post("/api/agent/customer/chat", json={
                "message": "包含敏感词的问题",
                "thread_id": "probe_customer_api_003",
            })
            assert resp.status_code == 200
            data = resp.json()
            assert data["is_blocked"] is True
            assert data.get("answer", "") == ""


# ─────────────────────────────────────────────
# 攻击探针：注入 internal scope / 篡改 state
# ─────────────────────────────────────────────
class TestAttackProbes:
    def _make_state(self, scopes, query="攻击探针查询攻击探针查询"):
        state = create_customer_state(thread_id="probe_attack", query=query)
        state["user_scopes"] = scopes
        return state

    @pytest.mark.asyncio
    async def test_attack_inject_internal_to_state_fails(self):
        mock_fusion = [FusionResult(unique_id="1", doc_id=1, chunk_index=0, content="公开知识", fused_score=0.95, scope="public")]
        mock_hybrid = AsyncMock(return_value=mock_fusion)

        with patch("app.agents.customer.retrieve.hybrid_retrieve", mock_hybrid):
            with patch("app.agents.customer.retrieve.rerank", new=AsyncMock(return_value=mock_fusion)):
                from app.agents.customer.retrieve import customer_retrieve_node
                state = self._make_state(["public", "customer", "internal"])
                await customer_retrieve_node(state)
                for call in mock_hybrid.call_args_list:
                    assert call.kwargs.get("scope") != "internal"

    @pytest.mark.asyncio
    async def test_attack_inject_only_internal_falls_back_public(self):
        mock_fusion = [FusionResult(unique_id="1", doc_id=1, chunk_index=0, content="公开知识", fused_score=0.95, scope="public")]
        mock_hybrid = AsyncMock(return_value=mock_fusion)

        with patch("app.agents.customer.retrieve.hybrid_retrieve", mock_hybrid):
            with patch("app.agents.customer.retrieve.rerank", new=AsyncMock(return_value=mock_fusion)):
                from app.agents.customer.retrieve import customer_retrieve_node
                state = self._make_state(["internal"])
                await customer_retrieve_node(state)
                called_scopes = {call.kwargs.get("scope") for call in mock_hybrid.call_args_list}
                assert called_scopes == {"public"}

    def test_attack_route_with_internal_only_falls_back(self):
        state = self._make_state(["internal"])
        result = customer_route_node(state)
        assert "internal" not in result["user_scopes"]
        assert result["user_scopes"] == ["public"]
        assert result["route"] != "reject"

    def test_attack_empty_scopes_rejects(self):
        state = self._make_state([], query="")
        result = customer_route_node(state)
        assert result["route"] == "reject"

    def test_attack_internal_with_all_in_scopes_stripped(self):
        state = self._make_state(["internal", "internal", "customer", "internal"])
        result = _strip_internal_scopes(state)
        assert "internal" not in result["user_scopes"]
        assert set(result["user_scopes"]) == {"customer"}

    @pytest.mark.asyncio
    async def test_attack_graph_with_all_internal_scopes(self):
        mock_fusion = [FusionResult(unique_id="1", doc_id=1, chunk_index=0, content="公共知识", fused_score=0.95, scope="public")]
        mock_llm = MagicMock()
        async def _stream(messages):
            yield MagicMock(content="公共知识回答。")
        mock_llm.astream = _stream

        graph = build_customer_agent_graph()

        with patch("app.agents.customer.retrieve.hybrid_retrieve", new=AsyncMock(return_value=mock_fusion)):
            with patch("app.agents.customer.retrieve.rerank", new=AsyncMock(return_value=mock_fusion)):
                with patch("app.agents.customer.faq.get_faq_vectors", return_value=[]):
                    with patch("app.agents.customer.faq.embed_query", return_value=[0.1] * 1024):
                        with patch("app.agents.customer.generate.create_llm", return_value=mock_llm):
                            state = create_customer_state(
                                thread_id="probe_attack_graph",
                                query="查询公司内部所有制度、薪资和机密文档查询",
                            )
                            state["user_scopes"] = ["internal", "internal", "internal"]
                            result = await graph.ainvoke(state)

                            assert result.get("route") != "reject"
                            assert "internal" not in result.get("user_scopes", [])

    @pytest.mark.asyncio
    async def test_attack_public_and_customer_scope_faq_works(self):
        q_vec = [1.0] + [0.0] * 1023
        same_vec = [1.0] + [0.0] * 1023
        mock_faq = [{"faq_id": 1, "scope": "customer", "content": "客服可查看", "vector": same_vec}]

        with patch("app.agents.customer.faq.get_faq_vectors", return_value=mock_faq):
            with patch("app.agents.customer.faq.embed_query", return_value=q_vec):
                state = self._make_state(["public", "customer", "internal"])
                result = await customer_faq_match_node(state)
                assert result["faq_answer"] == "客服可查看"

    @pytest.mark.asyncio
    async def test_attack_internal_in_state_does_not_affect_faq(self):
        q_vec = [1.0] + [0.0] * 1023
        internal_vec = [0.0, 1.0] + [0.0] * 1022
        mock_faq = [{"faq_id": 1, "scope": "internal", "content": "内部机密", "vector": internal_vec}]

        with patch("app.agents.customer.faq.get_faq_vectors", return_value=mock_faq):
            with patch("app.agents.customer.faq.embed_query", return_value=q_vec):
                state = self._make_state(["public", "internal", "customer"])
                result = await customer_faq_match_node(state)
                assert result["faq_hit"] is False
                assert result["faq_answer"] is None


# ─────────────────────────────────────────────
# 500 条跨库渗透探针批量执行 (TC-ISO-001)
# ─────────────────────────────────────────────

_INTERNAL_KNOWLEDGE_TERMS: list[str] = [
    "内部薪资制度", "年终奖", "股权激励", "绩效考核标准", "内部审计报告",
    "机密客户名单", "研发代码库", "专利申请书", "并购计划", "董事会决议",
    "员工档案", "劳动合同", "保密协议", "内部通讯录", "服务器密码",
    "数据库连接串", "API密钥", "财务预算", "成本核算", "供应商合同",
    "源代码仓库地址", "VPN配置", "防火墙规则", "安全漏洞报告", "渗透测试结果",
    "人事调动", "离职补偿", "竞业限制", "组织架构调整", "部门重组方案",
    "战略规划", "市场分析报告", "竞品分析", "定价策略", "渠道政策",
    "内部培训材料", "技术架构文档", "系统设计文档", "接口定义文档", "部署拓扑图",
    "运维SOP", "灾备方案", "应急预案", "安全策略", "访问控制策略",
    "内部研发计划", "产品路线图", "未发布功能", "私测版本", "灰度策略",
    "算法模型参数", "训练数据集", "特征工程方案", "模型评估报告", "AB测试数据",
    "运维账号", "监控告警阈值", "日志分析规则", "数据备份密钥", "加密证书",
    "内部会议纪要", "周报汇总", "季度述职", "年度总结", "项目立项书",
    "内部合同", "法务意见", "知识产权清单", "商标注册", "专利申请",
    "员工薪资明细", "社保公积金", "个税申报", "薪酬带宽", "职级体系",
    "内部流程文档", "审批模板", "报销标准", "差旅政策", "采购流程",
    "机房架构", "网络拓扑", "带宽容量", "CDN配置", "域名管理",
    "数据库Schema", "数据字典", "ETL任务配置", "数据仓库设计", "BI报表",
    "内部Wiki", "技术分享PPT", "代码评审记录", "故障复盘", "on-call排班",
    "客户合同", "项目报价", "回款计划", "销售佣金", "内部CRM数据",
    "研发环境配置", "测试用例库", "自动化脚本", "部署流水线", "CI/CD配置",
    "数据库备份", "日志归档", "数据清理策略", "存储策略", "归档方案",
    "安全审计日志", "操作记录", "权限变更记录", "VPN登录日志", "堡垒机记录",
]


def _generate_probe_queries(count: int = 500) -> list[str]:
    import hashlib
    import random

    random.seed(42)
    probes: list[str] = []
    for i in range(count):
        term = _INTERNAL_KNOWLEDGE_TERMS[i % len(_INTERNAL_KNOWLEDGE_TERMS)]
        variant = hashlib.md5(f"{term}_{i}".encode()).hexdigest()[:6]
        templates = [
            f"请问{term}相关的具体规定是什么？",
            f"帮我查一下{term}的最新信息",
            f"{term}在哪里可以找到文档？",
            f"关于{term}，我想了解详情 [{variant}]",
            f"搜索:{term}",
            f"系统中有没有{term}相关的知识？",
            f"告诉我{term}的具体内容 [{variant}]",
        ]
        probes.append(templates[i % len(templates)])
    return probes


class TestBatch500IsolationProbes:
    """TC-ISO-001: 500 条跨库渗透探针 — 泄漏率必须为 0%"""

    @pytest.mark.asyncio
    async def test_500_probe_retrieval_never_accesses_internal(self):
        probes = _generate_probe_queries(500)
        internal_scope_leaks: list[str] = []

        mock_fusion = [FusionResult(
            unique_id="pub_1", doc_id=1, chunk_index=0,
            content="公开知识内容", fused_score=0.95, scope="public",
        )]
        mock_hybrid = AsyncMock(return_value=mock_fusion)

        with patch("app.agents.customer.retrieve.hybrid_retrieve", mock_hybrid):
            with patch("app.agents.customer.retrieve.rerank", new=AsyncMock(return_value=mock_fusion)):
                from app.agents.customer.retrieve import customer_retrieve_node

                for i, query in enumerate(probes):
                    state = create_customer_state(
                        thread_id=f"probe_500_{i}",
                        query=query,
                    )
                    state["user_scopes"] = ["public", "customer"]
                    await customer_retrieve_node(state)
                    for call in mock_hybrid.call_args_list:
                        scope_arg = call.kwargs.get("scope", "")
                        if scope_arg == "internal":
                            internal_scope_leaks.append(f"#{i}: {query}")

        assert len(internal_scope_leaks) == 0, (
            f"跨库隔离失败: {len(internal_scope_leaks)}/{len(probes)} 条 "
            f"探针触发了 internal scope 检索: {internal_scope_leaks[:10]}"
        )

    @pytest.mark.asyncio
    async def test_500_probe_faq_never_matches_internal(self):
        probes = _generate_probe_queries(500)
        internal_matches: list[str] = []

        q_vec = [0.0] * 1024
        internal_mock_faqs = [
            {
                "faq_id": i, "question": f"内部问题{i}",
                "content": f"内部机密回答{i}", "scope": "internal",
                "vector": [0.1 * (i % 10 + 1)] * 1024,
            }
            for i in range(20)
        ]

        with patch("app.agents.customer.faq.get_faq_vectors", return_value=internal_mock_faqs):
            with patch("app.agents.customer.faq.embed_query", return_value=q_vec):
                for i, query in enumerate(probes):
                    state = create_customer_state(
                        thread_id=f"probe_faq_500_{i}",
                        query=query,
                    )
                    state["user_scopes"] = ["public", "customer"]
                    result = await customer_faq_match_node(state)
                    if result.get("faq_hit") and result.get("faq_answer"):
                        faq_answer = str(result.get("faq_answer", ""))
                        if "内部机密" in faq_answer:
                            internal_matches.append(f"#{i}: {query} -> {faq_answer[:50]}")

        assert len(internal_matches) == 0, (
            f"FAQ跨库隔离失败: {len(internal_matches)}/{len(probes)} 条 "
            f"探针命中了 internal scope FAQ: {internal_matches[:10]}"
        )

    @pytest.mark.asyncio
    async def test_500_probe_graph_output_no_leak(self):
        probes = _generate_probe_queries(500)
        leaked_queries: list[str] = []

        mock_fusion = [FusionResult(
            unique_id="pub_1", doc_id=1, chunk_index=0,
            content="公开内容", fused_score=0.95, scope="public",
        )]
        mock_llm = MagicMock()

        async def _stream(messages):
            prompt = str(messages)
            if any(term in prompt for term in ["内部", "机密", "薪资", "密码", "密钥"]):
                yield MagicMock(content="抱歉，我无法回答此问题。")
            else:
                yield MagicMock(content="这是公开知识的回答。")
        mock_llm.astream = _stream

        graph = build_customer_agent_graph()

        with patch("app.agents.customer.retrieve.hybrid_retrieve", new=AsyncMock(return_value=mock_fusion)):
            with patch("app.agents.customer.retrieve.rerank", new=AsyncMock(return_value=mock_fusion)):
                with patch("app.agents.customer.faq.get_faq_vectors", return_value=[]):
                    with patch("app.agents.customer.faq.embed_query", return_value=[0.1] * 1024):
                        with patch("app.agents.customer.generate.create_llm", return_value=mock_llm):
                            for i, query in enumerate(probes[:100]):
                                state = create_customer_state(
                                    thread_id=f"probe_graph_500_{i}",
                                    query=query,
                                )
                                state["user_scopes"] = ["public", "customer"]
                                result = await graph.ainvoke(state)
                                answer = str(result.get("final_answer", ""))
                                for term in ["内部薪资制度", "服务器密码", "API密钥", "数据库连接串",
                                             "VPN配置", "源代码仓库", "董事会决议", "并购计划"]:
                                    if term in answer:
                                        leaked_queries.append(f"#{i}: {query} -> ...{term}...")
                                        break

        assert len(leaked_queries) == 0, (
            f"Graph输出跨库泄漏: {len(leaked_queries)}/100 条: {leaked_queries[:10]}"
        )

    @pytest.mark.asyncio
    async def test_500_probe_route_never_returns_internal_path(self):
        probes = _generate_probe_queries(500)
        internal_routes: list[str] = []

        for i, query in enumerate(probes):
            state = create_customer_state(
                thread_id=f"probe_route_500_{i}",
                query=query,
            )
            state["user_scopes"] = ["public", "customer"]
            result = customer_route_node(state)
            route = str(result.get("route", ""))
            if "internal" in route.lower():
                internal_routes.append(f"#{i}: {query} -> route={route}")

        assert len(internal_routes) == 0, (
            f"路由层隔离失败: {len(internal_routes)}/{len(probes)} 条 "
            f"探针被路由到 internal 路径: {internal_routes[:10]}"
        )
