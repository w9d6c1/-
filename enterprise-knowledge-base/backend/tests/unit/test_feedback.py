"""反馈列表 + 统计 API 测试"""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_list_feedbacks_returns_data(client: AsyncClient, token_factory):
    """GET /feedbacks 返回反馈列表"""
    token = await token_factory("fback1")
    await client.post(
        "/api/admin/feedbacks",
        json={"thread_id": "thr-1", "rating": "like"},
        headers={"Authorization": f"Bearer {token}"},
    )
    await client.post(
        "/api/admin/feedbacks",
        json={"thread_id": "thr-2", "rating": "dislike", "suggestion": "不够准确"},
        headers={"Authorization": f"Bearer {token}"},
    )

    resp = await client.get("/api/admin/feedbacks", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) >= 2


@pytest.mark.asyncio
async def test_list_feedbacks_with_rating_filter(client: AsyncClient, token_factory):
    """GET /feedbacks?rating=like 过滤"""
    token = await token_factory("fback2")
    await client.post("/api/admin/feedbacks", json={"thread_id": "thr-3", "rating": "like"}, headers={"Authorization": f"Bearer {token}"})
    await client.post("/api/admin/feedbacks", json={"thread_id": "thr-4", "rating": "dislike"}, headers={"Authorization": f"Bearer {token}"})

    resp = await client.get("/api/admin/feedbacks?rating=like", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    data = resp.json()
    for item in data:
        assert item["rating"] == "like"


@pytest.mark.asyncio
async def test_feedback_stats(client: AsyncClient, token_factory):
    """GET /feedbacks/stats 返回统计"""
    token = await token_factory("fback3")
    await client.post("/api/admin/feedbacks", json={"thread_id": "thr-5", "rating": "like"}, headers={"Authorization": f"Bearer {token}"})
    await client.post("/api/admin/feedbacks", json={"thread_id": "thr-6", "rating": "dislike"}, headers={"Authorization": f"Bearer {token}"})

    resp = await client.get("/api/admin/feedbacks/stats", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    data = resp.json()
    assert "total" in data
    assert "likes" in data
    assert "dislikes" in data
    assert data["total"] >= 2


@pytest.mark.asyncio
async def test_list_feedbacks_empty(client: AsyncClient, token_factory):
    """空列表也返回 200"""
    token = await token_factory("fback4")
    resp = await client.get("/api/admin/feedbacks", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    assert resp.json() == []
