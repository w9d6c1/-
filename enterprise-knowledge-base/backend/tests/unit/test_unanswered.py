"""未命中问题管理 API 测试"""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_list_unanswered_returns_data(client: AsyncClient, token_factory):
    """GET /unanswered 返回未命中列表"""
    token = await token_factory("unansw1")
    await client.post(
        "/api/admin/unanswered",
        json={"thread_id": "thr-a", "question": "不知道的问题1"},
        headers={"Authorization": f"Bearer {token}"},
    )
    await client.post(
        "/api/admin/unanswered",
        json={"thread_id": "thr-b", "question": "不知道的问题2", "source": "internal"},
        headers={"Authorization": f"Bearer {token}"},
    )

    resp = await client.get("/api/admin/unanswered", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) >= 2


@pytest.mark.asyncio
async def test_list_unanswered_filter_by_status(client: AsyncClient, token_factory):
    """GET /unanswered?status=pending 过滤"""
    token = await token_factory("unansw2")
    await client.post(
        "/api/admin/unanswered",
        json={"thread_id": "thr-c", "question": "待处理"},
        headers={"Authorization": f"Bearer {token}"},
    )

    resp = await client.get("/api/admin/unanswered?status=pending", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    data = resp.json()
    for item in data:
        assert item["status"] == "pending"


@pytest.mark.asyncio
async def test_patch_unanswered_status(client: AsyncClient, token_factory):
    """PATCH /unanswered/{id} 更新状态"""
    token = await token_factory("unansw3")
    resp = await client.post(
        "/api/admin/unanswered",
        json={"thread_id": "thr-d", "question": "待忽略"},
        headers={"Authorization": f"Bearer {token}"},
    )
    ua_id = resp.json()["id"]

    resp = await client.patch(
        f"/api/admin/unanswered/{ua_id}",
        json={"status": "ignored"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ignored"


@pytest.mark.asyncio
async def test_convert_unanswered_to_faq(client: AsyncClient, token_factory):
    """POST /unanswered/{id}/convert 转为 FAQ 草稿"""
    token = await token_factory("unansw4")
    resp = await client.post(
        "/api/admin/unanswered",
        json={"thread_id": "thr-e", "question": "产品保修期多久"},
        headers={"Authorization": f"Bearer {token}"},
    )
    ua_id = resp.json()["id"]

    resp = await client.post(
        f"/api/admin/unanswered/{ua_id}/convert",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "faq_id" in data
    assert "question" in data
    assert "generated_answer" in data


@pytest.mark.asyncio
async def test_list_unanswered_empty(client: AsyncClient, token_factory):
    """空列表也返回 200"""
    token = await token_factory("unansw5")
    resp = await client.get("/api/admin/unanswered", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    assert resp.json() == []
