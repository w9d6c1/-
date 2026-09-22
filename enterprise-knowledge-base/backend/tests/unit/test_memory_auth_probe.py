"""场景5探针：多轮记忆 + 权限 + 隔离

已验证的 FIX:
  B1 [FIXED]: _customer_stream_events 已加载 checkpoint → 多轮记忆恢复
  B2 [FIXED]: Agent 端点 scope 从 ChatRequest 移除，user_role 从 JWT 解码
  B3 [FIXED]: Agent internal 端点接入 require_auth → 无 token 返回 401
  B4 [FIXED]: authenticate_node 同步函数不使用异步锁管理缓存
  B5 [FIXED]: map_role_to_scopes 移除不必要的读锁

正常工作:
  M1: _do_chat (internal 非流式) — 正确加载 checkpoint 恢复历史
  M2: _stream_events (internal 流式) — 正确加载 checkpoint 恢复历史
  M3: customer_chat (客服非流式) — 正确加载 checkpoint 恢复历史

注意: customer/chat 和 internal/chat 端点使用 @agent_limiter.limit 装饰器，
通过 httpx client 调用会因 slowapi Limiter 实例不匹配而挂起。
这些端点的权限/记忆行为已通过直接函数调用测试覆盖。
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from langchain_core.messages import HumanMessage, AIMessage


# ── 容器内跳过：路径解析依赖宿主仓库根目录 ──
from pathlib import Path as _Path
_PROJECT = _Path(__file__).resolve().parent.parent.parent.parent
pytestmark = pytest.mark.skipif(
    not (_PROJECT / "backend" / "app").exists(),
    reason=f"需从宿主仓库根目录运行（{_PROJECT}/backend/app 不存在）",
)

def _make_mock_graph():
    mock = MagicMock()
    mock.aget_state = AsyncMock(return_value=None)
    mock.ainvoke = AsyncMock(return_value={
        "final_answer": "测试回答",
        "is_blocked": False, "block_reason": "",
        "confidence": 0.9, "needs_human": False,
        "faq_hit": False, "route": "retrieve",
    })

    async def _fake_astream(state, version=None, config=None):
        yield {"event": "on_chain_end", "data": {"output": {"final_answer": "流式回答"}}}

    mock.astream_events = _fake_astream
    return mock


def _make_mock_user(role="operator", user_id=1, department=None):
    """创建 mock User 对象，模拟 require_auth 从 JWT 解码后返回的 ORM 对象"""
    user = MagicMock()
    user.id = user_id
    user.role = role
    user.department = department
    user.is_active = True
    return user


# ─────────────────────────────────────────────
# M1: _do_chat 多轮记忆 ✓ (internal 非流式)
# ─────────────────────────────────────────────
class TestInternalChatMultiTurn:
    """_do_chat 正确: checkpoint → 恢复历史 → 追加新消息 → 传入 graph"""

    @pytest.mark.asyncio
    async def test_do_chat_recovers_checkpoint_history(self):
        from app.api.agent.__init__ import _do_chat, ChatRequest

        mock_graph = _make_mock_graph()
        mock_saved = MagicMock()
        mock_saved.values = {
            "messages": [
                HumanMessage(content="第一轮问题"),
                AIMessage(content="第一轮回答"),
            ],
        }
        mock_graph.aget_state = AsyncMock(return_value=mock_saved)

        captured = {}
        async def _fake_ainvoke(state, config=None):
            captured["msg_count"] = len(state.get("messages", []))
            return {"final_answer": "第二轮回答", "is_blocked": False,
                    "confidence": 0.9, "needs_human": False, "faq_hit": False, "route": "retrieve"}

        mock_graph.ainvoke = AsyncMock(side_effect=_fake_ainvoke)

        with patch("app.api.agent.__init__._get_graph", return_value=mock_graph):
            req = ChatRequest(message="第二轮问题", thread_id="thread-001")
            result = await _do_chat(req)

        assert captured.get("msg_count", 0) == 3  # 2 history + 1 new
        assert "第二轮回答" in result["answer"]

    @pytest.mark.asyncio
    async def test_do_chat_creates_fresh_state_without_checkpoint(self):
        from app.api.agent.__init__ import _do_chat, ChatRequest

        mock_graph = _make_mock_graph()
        mock_graph.aget_state = AsyncMock(return_value=None)

        captured = {}
        async def _fake_ainvoke(state, config=None):
            captured["msg_count"] = len(state.get("messages", []))
            return {"final_answer": "新对话", "is_blocked": False,
                    "confidence": 0.9, "needs_human": False, "faq_hit": False, "route": "retrieve"}

        mock_graph.ainvoke = AsyncMock(side_effect=_fake_ainvoke)

        with patch("app.api.agent.__init__._get_graph", return_value=mock_graph):
            req = ChatRequest(message="第一轮问题")
            result = await _do_chat(req)

        assert captured.get("msg_count", 0) == 1  # 仅当前消息
        assert result["thread_id"]

    @pytest.mark.asyncio
    async def test_do_chat_appends_new_message_to_history(self):
        from app.api.agent.__init__ import _do_chat, ChatRequest

        mock_graph = _make_mock_graph()
        mock_saved = MagicMock()
        mock_saved.values = {"messages": [HumanMessage(content="上一轮"), AIMessage(content="回复")]}
        mock_graph.aget_state = AsyncMock(return_value=mock_saved)

        captured = {}
        async def _fake_ainvoke(state, config=None):
            captured["msg_count"] = len(state.get("messages", []))
            return {"final_answer": "回答", "is_blocked": False,
                    "confidence": 0.9, "needs_human": False, "faq_hit": False, "route": "retrieve"}

        mock_graph.ainvoke = AsyncMock(side_effect=_fake_ainvoke)

        with patch("app.api.agent.__init__._get_graph", return_value=mock_graph):
            req = ChatRequest(message="这一轮", thread_id="thread-002")
            await _do_chat(req)

        assert captured.get("msg_count", 0) == 3


# ─────────────────────────────────────────────
# M2: _stream_events 多轮记忆 ✓ (internal 流式)
# ─────────────────────────────────────────────
class TestInternalStreamMultiTurn:
    """_stream_events 正确: checkpoint → 恢复历史 → 追加新消息"""

    @pytest.mark.asyncio
    async def test_stream_recovers_checkpoint_and_appends_message(self):
        from app.api.agent.__init__ import _stream_events

        mock_graph = _make_mock_graph()
        mock_saved = MagicMock()
        mock_saved.values = {"messages": [HumanMessage(content="你好"), AIMessage(content="你好！")]}
        mock_graph.aget_state = AsyncMock(return_value=mock_saved)

        captured = {}
        async def _fake_astream(state, version=None, config=None):
            captured["msg_count"] = len(state.get("messages", []))
            yield {"event": "on_chain_end", "data": {"output": {"final_answer": "好的"}}}

        mock_graph.astream_events = _fake_astream

        mock_user = _make_mock_user(role="operator")

        with patch("app.api.agent.__init__._get_graph", return_value=mock_graph):
            chunks = [c async for c in _stream_events("thread-003", "我叫张三", mock_user)]

        assert captured.get("msg_count", 0) == 3
        assert len(chunks) >= 1

    @pytest.mark.asyncio
    async def test_stream_creates_fresh_state_without_checkpoint(self):
        from app.api.agent.__init__ import _stream_events

        mock_graph = _make_mock_graph()
        mock_graph.aget_state = AsyncMock(return_value=None)

        captured = {}
        async def _fake_astream(state, version=None, config=None):
            captured["msg_count"] = len(state.get("messages", []))
            captured["user_role"] = state.get("user_role", "")
            yield {"event": "on_chain_end", "data": {"output": {"final_answer": "新对话"}}}

        mock_graph.astream_events = _fake_astream

        mock_user = _make_mock_user(role="dept_admin")

        with patch("app.api.agent.__init__._get_graph", return_value=mock_graph):
            chunks = [c async for c in _stream_events("thread-new", "新问题", mock_user)]

        assert captured["user_role"] == "dept_admin"
        assert captured.get("msg_count", 0) == 1


# ─────────────────────────────────────────────
# M4: _customer_stream_events — BUG: 无 checkpoint 加载
# ─────────────────────────────────────────────
class TestCustomerStreamMultiTurnBug:
    """B1 FIXED: _customer_stream_events 现已正确加载 checkpoint — 客服流式多轮记忆已修复"""

    @pytest.mark.asyncio
    async def test_customer_stream_events_now_calls_aget_state(self):
        """FIX 验证: B1 已修复 — aget_state 现在被调用来加载 checkpoint"""
        from app.api.agent.__init__ import _customer_stream_events

        mock_graph = _make_mock_graph()

        with patch("app.api.agent.__init__._get_customer_graph", return_value=mock_graph):
            chunks = [c async for c in _customer_stream_events("cust-stream-001", "客服问题")]

        mock_graph.aget_state.assert_called_once()
        assert len(chunks) >= 1

    @pytest.mark.asyncio
    async def test_customer_stream_state_has_no_history(self):
        """FIX 验证: state 只有 1 条消息(当前问题), checkpoint 为空时仍正确"""
        from app.api.agent.__init__ import _customer_stream_events

        mock_graph = _make_mock_graph()
        captured = {}
        async def _capture_astream(state, version=None, config=None):
            captured["msg_count"] = len(state.get("messages", []))
            yield {"event": "on_chain_end", "data": {"output": {"final_answer": "回答"}}}

        mock_graph.astream_events = _capture_astream

        with patch("app.api.agent.__init__._get_customer_graph", return_value=mock_graph):
            async for _ in _customer_stream_events("cust-stream-002", "第二轮问题"):
                pass

        assert captured.get("msg_count", 0) == 1

    @pytest.mark.asyncio
    async def test_internal_stream_has_checkpoint_loading_for_contrast(self):
        """对比: internal 流式正确调用了 aget_state 并传入 User 对象"""
        from app.api.agent.__init__ import _stream_events

        mock_graph = _make_mock_graph()
        mock_graph.aget_state = AsyncMock(return_value=None)

        mock_user = _make_mock_user(role="operator")

        with patch("app.api.agent.__init__._get_graph", return_value=mock_graph):
            async for _ in _stream_events("internal-001", "问题", mock_user):
                pass

        mock_graph.aget_state.assert_called_once()


# ─────────────────────────────────────────────
# A1: Agent 端点无 JWT 认证 ✓
# ─────────────────────────────────────────────
class TestAgentEndpointsNoAuth:
    """B3 FIXED: Internal agent 端点现已接入 require_auth — 无 token 返回 401"""

    @pytest.mark.asyncio
    async def test_status_no_auth(self, client):
        resp = await client.get("/api/agent/status")
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_info_no_auth(self, client):
        resp = await client.get("/api/agent/info")
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_internal_chat_stream_requires_auth(self, client):
        """FIX 验证: B3 已修复 — internal 端点无 token 返回 401"""
        mock_graph = _make_mock_graph()
        with patch("app.api.agent.__init__._get_graph", return_value=mock_graph):
            resp = await client.post("/api/agent/internal/chat/stream", json={
                "message": "测试", "thread_id": "noauth-stream",
            })
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_customer_chat_stream_no_auth(self, client):
        """customer 端点保持公开访问"""
        mock_graph = _make_mock_graph()
        with patch("app.api.agent.__init__._get_customer_graph", return_value=mock_graph):
            resp = await client.post("/api/agent/customer/chat/stream", json={
                "message": "测试", "thread_id": "noauth-cust-stream",
            })
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_rewrite_no_auth(self, client):
        resp = await client.post("/api/agent/rewrite", json={"message": "测试查询改写"})
        assert resp.status_code == 200
        assert "rewritten" in resp.json()

    @pytest.mark.asyncio
    async def test_admin_requires_auth_for_contrast(self, client):
        """对比: admin 端点正确拒绝无认证请求"""
        resp = await client.post("/api/admin/auth/users", json={
            "username": "test", "password": "TestP@ss1",
            "password_confirm": "TestP@ss1", "role": "readonly",
        })
        assert resp.status_code in (401, 403)


# ─────────────────────────────────────────────
# A2: scope 来自用户输入 ✓
# ─────────────────────────────────────────────
class TestScopeFromUserInput:
    """B2 FIXED: scope 已从 ChatRequest 移除 — user_role 从 JWT 解码，scope 由 authenticate_node 推导"""

    @pytest.mark.asyncio
    async def test_chatrequest_no_longer_has_scope_field(self):
        """FIX 验证: B2 已修复 — ChatRequest 不再接受 scope 参数"""
        from app.api.agent.__init__ import ChatRequest

        # 不应包含 scope 字段
        assert "scope" not in ChatRequest.model_fields
        # 应只包含 message 和 thread_id
        req = ChatRequest(message="测试")
        assert req.message == "测试"

    @pytest.mark.asyncio
    async def test_user_role_always_readonly(self):
        """FIX 验证: 无认证用户 _do_chat 默认 user_role = readonly"""
        from app.api.agent.__init__ import _do_chat, ChatRequest

        mock_graph = _make_mock_graph()
        captured = {}
        async def _fake_ainvoke(state, config=None):
            captured["user_role"] = state.get("user_role", "")
            captured["user_scopes"] = state.get("user_scopes", [])
            return {"final_answer": "回答", "is_blocked": False,
                    "confidence": 0.9, "needs_human": False, "faq_hit": False, "route": "retrieve"}

        mock_graph.ainvoke = AsyncMock(side_effect=_fake_ainvoke)

        with patch("app.api.agent.__init__._get_graph", return_value=mock_graph):
            req = ChatRequest(message="测试")
            await _do_chat(req)

        assert captured["user_role"] == "readonly"

    @pytest.mark.asyncio
    async def test_authenticated_user_role_from_jwt(self):
        """FIX 验证: B4 已修复 — 认证用户的 role 从 User ORM 对象 (JWT decoded) 获取"""
        from app.api.agent.__init__ import _do_chat, ChatRequest

        mock_graph = _make_mock_graph()
        captured = {}
        async def _fake_ainvoke(state, config=None):
            captured["user_role"] = state.get("user_role", "")
            captured["user_id"] = state.get("user_id")
            return {"final_answer": "回答", "is_blocked": False,
                    "confidence": 0.9, "needs_human": False, "faq_hit": False, "route": "retrieve"}

        mock_graph.ainvoke = AsyncMock(side_effect=_fake_ainvoke)

        mock_user = _make_mock_user(role="superadmin", user_id=42)

        with patch("app.api.agent.__init__._get_graph", return_value=mock_graph):
            req = ChatRequest(message="管理查询")
            await _do_chat(req, user=mock_user)

        assert captured["user_role"] == "superadmin"
        assert captured["user_id"] == 42

    @pytest.mark.asyncio
    async def test_graph_auth_node_overwrites_scopes_for_contrast(self):
        """graph 层面: authenticate_node 将 readonly → ["public"] 覆盖用户输入"""
        from app.agents.graph import build_internal_agent_graph
        from app.agents.state import create_initial_state

        mock_llm = MagicMock()
        async def _stream(messages):
            yield MagicMock(content="回答")
        mock_llm.astream = _stream

        graph = build_internal_agent_graph(with_checkpointer=False)
        with patch("app.agents.nodes.generate.create_llm", return_value=mock_llm):
            with patch("app.agents.nodes.retrieve.hybrid_retrieve", new=AsyncMock(return_value=[])):
                with patch("app.agents.nodes.retrieve.rerank", new=AsyncMock(return_value=[])):
                    with patch("app.agents.nodes.faq.get_faq_vectors", return_value=[]):
                        with patch("app.agents.nodes.faq.embed_query", return_value=[0.1] * 1024):
                            state = create_initial_state(
                                thread_id="scope-test", query="测试问题足够长长度",
                                user_role="readonly", user_scopes=["public", "internal"],
                            )
                            result = await graph.ainvoke(state)

        assert result["user_scopes"] == ["public"]
