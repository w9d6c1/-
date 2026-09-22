"""管理仪表盘统计 API 测试 (TDD: RED)"""

import pytest
from httpx import AsyncClient


async def _register_and_login(client: AsyncClient, username: str, role: str = "operator") -> str:
    await client.post(
        "/api/admin/auth/register",
        json={"username": username, "password": "SecureP@ss1", "password_confirm": "SecureP@ss1", "role": role},
    )
    resp = await client.post(
        "/api/admin/auth/login",
        data={"username": username, "password": "SecureP@ss1"},
    )
    return resp.json()["access_token"]


@pytest.mark.asyncio
async def test_dashboard_stats_returns_data(client: AsyncClient):
    """GET /dashboard/stats 返回统计字段"""
    token = await _register_and_login(client, "dash1")
    resp = await client.get("/api/admin/dashboard/stats", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    data = resp.json()
    assert "today_chats" in data
    assert "faq_hit_rate" in data
    assert "feedback_good_rate" in data
    assert "pending_reviews" in data
    assert "pending_unanswered" in data
    assert "trend" in data
    assert len(data["trend"]) == 7


@pytest.mark.asyncio
async def test_dashboard_stats_requires_auth(client: AsyncClient):
    """无 token 返回 401"""
    resp = await client.get("/api/admin/dashboard/stats")
    assert resp.status_code == 401
