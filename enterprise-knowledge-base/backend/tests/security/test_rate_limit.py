"""安全测试 — 速率限制 (rate limiting) 在 API 层生效"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.fixture(autouse=True)
def _reset_rate_limits():
    from app.api.agent import agent_limiter
    from app.api.admin.auth import limiter as auth_limiter

    agent_limiter.reset()
    auth_limiter.reset()
    yield
    agent_limiter.reset()
    auth_limiter.reset()


class TestAgentRateLimit:
    @pytest.mark.asyncio
    async def test_internal_chat_limited_to_30_per_minute(self, client):
        from app.api.agent import agent_limiter

        mock_graph = MagicMock()
        mock_graph.ainvoke = AsyncMock(
            return_value={
                "final_answer": "ok",
                "is_blocked": False,
                "confidence": 0.9,
                "needs_human": False,
                "faq_hit": False,
                "route": "faq",
                "citations": [],
                "doc_images": [],
            }
        )
        mock_graph.aget_state = AsyncMock(return_value=None)
        mock_graph.aupdate_state = AsyncMock()

        with patch("app.api.agent._agent_graph", mock_graph):
            for _ in range(30):
                resp = await client.post("/api/agent/internal/chat", json={"message": "hi"})
                assert resp.status_code == 200, resp.text

            # 第 31 次应被限流
            resp = await client.post("/api/agent/internal/chat", json={"message": "hi"})
            assert resp.status_code == 429

    @pytest.mark.asyncio
    async def test_public_customer_chat_is_not_blocked_after_internal_use(self, client):
        """不同限流器独立生效 —— 客服(60/min) 不受内部(30/min) 限流影响。"""
        from app.api.agent import agent_limiter

        # 触发内部限流(31 次)
        mock_graph = MagicMock()
        mock_graph.ainvoke = AsyncMock(
            return_value={
                "final_answer": "ok",
                "is_blocked": False,
                "confidence": 0.9,
                "needs_human": False,
                "faq_hit": False,
                "route": "faq",
                "citations": [],
                "doc_images": [],
            }
        )
        mock_graph.aget_state = AsyncMock(return_value=None)
        mock_graph.aupdate_state = AsyncMock()

        with patch("app.api.agent._agent_graph", mock_graph):
            for _ in range(30):
                await client.post("/api/agent/internal/chat", json={"message": "hi"})
            resp = await client.post("/api/agent/internal/chat", json={"message": "hi"})
            assert resp.status_code == 429

        # 客服端点(不同 limit key) 不受影响
        mock_cust = MagicMock()
        mock_cust.ainvoke = AsyncMock(
            return_value={
                "final_answer": "客服ok",
                "is_blocked": False,
                "confidence": 0.9,
                "needs_human": False,
                "faq_hit": False,
                "route": "faq",
                "citations": [],
                "doc_images": [],
            }
        )
        mock_cust.aget_state = AsyncMock(return_value=None)
        mock_cust.aupdate_state = AsyncMock()

        with patch("app.api.agent._customer_graph", mock_cust):
            resp = await client.post("/api/agent/customer/chat", json={"message": "hi"})
            assert resp.status_code == 200
            assert "客服ok" in resp.json()["answer"]


class TestLoginRateLimit:
    def test_rate_limit_disabled_in_debug_mode(self):
        """_rate_limit 在 debug 模式下直接返回原函数（限流旁路）。"""
        from app.api.admin import auth as auth_mod
        from app.core.config import settings

        def dummy(request):
            return "x"

        old = settings.debug
        try:
            settings.debug = True
            wrapped = auth_mod._rate_limit("10/minute")(dummy)
            assert wrapped is dummy

            settings.debug = False
            wrapped = auth_mod._rate_limit("10/minute")(dummy)
            assert wrapped is not dummy
        finally:
            settings.debug = old
