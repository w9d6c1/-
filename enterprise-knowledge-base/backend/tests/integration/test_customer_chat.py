"""集成测试 — 客服对话流程 + 人工转接"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


class TestCustomerChatFlow:
    async def _login(self, client):
        await client.post("/api/admin/auth/register", json={
            "username": "cust_chat_1", "password": "CustChat1!",
            "password_confirm": "CustChat1!", "display_name": "Cust Chat",
            "role": "superadmin",
        })
        resp = await client.post("/api/admin/auth/login", data={
            "username": "cust_chat_1", "password": "CustChat1!",
        })
        return resp.json()["access_token"]

    @pytest.mark.asyncio
    async def test_customer_chat_endpoint_responds(self, client):
        mock_graph = MagicMock()
        mock_graph.ainvoke = AsyncMock(return_value={
            "final_answer": "您好，这里是客服助手。",
            "is_blocked": False,
            "confidence": 0.85,
            "needs_human": False,
            "faq_hit": False,
            "route": "",
        })

        with patch("app.api.agent._customer_graph", mock_graph):
            resp = await client.post("/api/agent/customer/chat", json={
                "message": "请问退换货流程是什么？",
            })
            assert resp.status_code == 200
            data = resp.json()
            assert "answer" in data
            assert not data.get("is_blocked", True)

    @pytest.mark.asyncio
    async def test_customer_chat_sse_streaming(self, client):
        mock_graph = MagicMock()

        async def _empty_stream(*args, **kwargs):
            return
            yield

        mock_graph.astream_events = _empty_stream

        with patch("app.api.agent._customer_graph", mock_graph):
            resp = await client.post("/api/agent/customer/chat/stream", json={
                "message": "查询订单",
                "thread_id": "test_stream_thread",
            })
            assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_customer_chat_with_sensitive_word_blocked(self, client):
        mock_graph = MagicMock()
        mock_graph.ainvoke = AsyncMock(return_value={
            "final_answer": "",
            "is_blocked": True,
            "block_reason": "包含敏感词",
            "confidence": 0.0,
            "needs_human": False,
            "faq_hit": False,
            "route": "",
        })

        with patch("app.api.agent._customer_graph", mock_graph):
            resp = await client.post("/api/agent/customer/chat", json={
                "message": "包含敏感词的问题",
            })
            assert resp.status_code == 200
            data = resp.json()
            assert data["is_blocked"] is True
