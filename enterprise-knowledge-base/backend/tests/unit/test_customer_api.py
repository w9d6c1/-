"""客服 API 端点测试 (TDD: RED)"""

import json
from unittest.mock import MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.fixture(autouse=True)
def _reset_customer_graph():
    import app.api.agent as agent_module

    agent_module._customer_graph = None


class TestCustomerChatAPI:
    @pytest.mark.asyncio
    async def test_chat_returns_answer(self):
        """客服 /agent/customer/chat 返回回答"""
        mock_graph = MagicMock()

        async def _ainvoke(state, config=None):
            return {"final_answer": "您可以在订单页面提交退货申请。", "is_blocked": False, "block_reason": "", "confidence": 0.85, "needs_human": False, "human_reason": "", "faq_hit": False, "route": "retrieve"}

        mock_graph.ainvoke = _ainvoke

        with patch("app.api.agent.build_customer_agent_graph", return_value=mock_graph):
            async with ASGITransport(app=app) as transport:
                async with AsyncClient(transport=transport, base_url="http://test") as client:
                    resp = await client.post("/api/agent/customer/chat", json={
                        "message": "如何退货",
                        "thread_id": "test-thread-1",
                    })

        assert resp.status_code == 200
        data = resp.json()
        assert "thread_id" in data
        assert "answer" in data
        assert data["answer"] == "您可以在订单页面提交退货申请。"
        assert "confidence" in data
        assert data["confidence"] == 0.85
        assert "needs_human" in data

    @pytest.mark.asyncio
    async def test_chat_without_thread_id_generates_one(self):
        """不传 thread_id 自动生成"""
        mock_graph = MagicMock()

        async def _ainvoke(state, config=None):
            return {"final_answer": "ok", "is_blocked": False, "confidence": 0.5, "needs_human": False, "human_reason": "", "faq_hit": False, "route": "faq"}

        mock_graph.ainvoke = _ainvoke

        with patch("app.api.agent.build_customer_agent_graph", return_value=mock_graph):
            async with ASGITransport(app=app) as transport:
                async with AsyncClient(transport=transport, base_url="http://test") as client:
                    resp = await client.post("/api/agent/customer/chat", json={
                        "message": "退货流程",
                    })

        assert resp.status_code == 200
        data = resp.json()
        assert len(data["thread_id"]) > 0

    @pytest.mark.asyncio
    async def test_chat_blocked_query(self):
        """被拦截的查询返回 is_blocked=True"""
        mock_graph = MagicMock()

        async def _ainvoke(state, config=None):
            return {"final_answer": "", "is_blocked": True, "block_reason": "forbid_word", "confidence": 0.0, "needs_human": False, "human_reason": "", "faq_hit": False, "route": "reject"}

        mock_graph.ainvoke = _ainvoke

        with patch("app.api.agent.build_customer_agent_graph", return_value=mock_graph):
            async with ASGITransport(app=app) as transport:
                async with AsyncClient(transport=transport, base_url="http://test") as client:
                    resp = await client.post("/api/agent/customer/chat", json={
                        "message": "禁止讨论",
                    })

        assert resp.status_code == 200
        data = resp.json()
        assert data["is_blocked"] is True
        assert data["answer"] == ""

    @pytest.mark.asyncio
    async def test_chat_needs_human(self):
        """转人工场景返回 needs_human=True"""
        mock_graph = MagicMock()

        async def _ainvoke(state, config=None):
            return {"final_answer": "需要转接人工", "is_blocked": False, "confidence": 0.4, "needs_human": True, "human_reason": "low_confidence:0.40", "faq_hit": False, "route": "retrieve"}

        mock_graph.ainvoke = _ainvoke

        with patch("app.api.agent.build_customer_agent_graph", return_value=mock_graph):
            async with ASGITransport(app=app) as transport:
                async with AsyncClient(transport=transport, base_url="http://test") as client:
                    resp = await client.post("/api/agent/customer/chat", json={
                        "message": "投诉退款",
                    })

        assert resp.status_code == 200
        data = resp.json()
        assert data["needs_human"] is True


class TestCustomerChatStreamAPI:
    @pytest.mark.asyncio
    async def test_stream_returns_sse_events(self):
        """SSE 流式返回 token 事件"""
        mock_graph = MagicMock()

        mock_chunk_1 = MagicMock()
        mock_chunk_1.content = "您"
        mock_chunk_2 = MagicMock()
        mock_chunk_2.content = "好"

        async def _stream_events(state, version=None, config=None):
            yield {"event": "on_chat_model_stream", "data": {"chunk": mock_chunk_1}}
            yield {"event": "on_chat_model_stream", "data": {"chunk": mock_chunk_2}}
            yield {"event": "on_chain_end", "data": {"output": {"final_answer": "您好", "confidence": 0.9, "needs_human": False}}}

        mock_graph.astream_events = _stream_events

        with patch("app.api.agent.build_customer_agent_graph", return_value=mock_graph):
            async with ASGITransport(app=app) as transport:
                async with AsyncClient(transport=transport, base_url="http://test") as client:
                    resp = await client.post("/api/agent/customer/chat/stream", json={
                        "message": "你好",
                    })

        assert resp.status_code == 200
        assert "text/event-stream" in resp.headers.get("content-type", "")
        body = resp.text
        assert "您" in body
        assert "好" in body
        assert "[DONE]" in body

    @pytest.mark.asyncio
    async def test_stream_handles_error_gracefully(self):
        """SSE 流式异常时静默结束"""
        mock_graph = MagicMock()

        async def _stream_errors(state, version=None, config=None):
            raise RuntimeError("simulated error")
            yield  # unreachable

        mock_graph.astream_events = _stream_errors

        with patch("app.api.agent.build_customer_agent_graph", return_value=mock_graph):
            async with ASGITransport(app=app) as transport:
                async with AsyncClient(transport=transport, base_url="http://test") as client:
                    resp = await client.post("/api/agent/customer/chat/stream", json={
                        "message": "出错测试",
                    })

        assert resp.status_code == 200
        assert "[DONE]" in resp.text
