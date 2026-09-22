"""部门数据隔离 + 权限守卫测试"""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_dept_admin_sees_only_own_dept_data(client: AsyncClient, token_factory):
    """部门管理员只能看到自己部门的数据"""
    token_a = await token_factory("admin_rd", "dept_admin", "研发部")
    await token_factory("admin_mkt", "dept_admin", "市场部")

    # 研发部管理员创建分类
    resp = await client.post(
        "/api/admin/categories",
        json={"name": "研发文档", "scope": "internal", "department": "研发部"},
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert resp.status_code == 201

    # 市场部管理员创建分类（用自己的 token）
    token_b_resp = await client.post(
        "/api/admin/auth/login",
        data={"username": "admin_mkt", "password": "SecureP@ss1"},
    )
    token_b = token_b_resp.json()["access_token"]
    resp = await client.post(
        "/api/admin/categories",
        json={"name": "市场文档", "scope": "public", "department": "市场部"},
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert resp.status_code == 201

    # 研发部管理员看列表，应该只有 "研发文档"
    resp = await client.get(
        "/api/admin/categories",
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    items = data["items"]
    assert len(items) == 1
    assert items[0]["name"] == "研发文档"


@pytest.mark.asyncio
async def test_superadmin_sees_all_data(client: AsyncClient, token_factory):
    """超管可以看到所有部门的数据"""
    token = await token_factory("super", "superadmin")

    # 创建两个不同部门的分类
    await client.post(
        "/api/admin/categories",
        json={"name": "全局文档", "scope": "public", "department": None},
        headers={"Authorization": f"Bearer {token}"},
    )
    resp = await client.post(
        "/api/admin/categories",
        json={"name": "内部文档", "scope": "internal", "department": "研发部"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201

    resp = await client.get(
        "/api/admin/categories",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert len(resp.json()["items"]) == 2


@pytest.mark.asyncio
async def test_readonly_user_cannot_write(client: AsyncClient, token_factory):
    """只读用户创建分类应返回 403"""
    token = await token_factory("reader", "readonly")

    resp = await client.post(
        "/api/admin/categories",
        json={"name": "测试分类", "scope": "public"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_readonly_user_can_read(client: AsyncClient, token_factory):
    """只读用户可以读取分类列表"""
    token = await token_factory("reader2", "readonly")

    resp = await client.get(
        "/api/admin/categories",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_no_token_returns_401(client: AsyncClient):
    """无 Token 无法访问分类 API"""
    resp = await client.get("/api/admin/categories")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_no_token_returns_401_on_write(client: AsyncClient):
    """无 Token 无法创建分类"""
    resp = await client.post("/api/admin/categories", json={"name": "x"})
    assert resp.status_code == 401
