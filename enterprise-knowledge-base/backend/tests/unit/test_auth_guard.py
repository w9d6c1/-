"""角色权限测试"""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_readonly_user_gets_403_on_create(client: AsyncClient, token_factory):
    """只读用户调用受保护 POST 应返回 403"""
    token = await token_factory("reader1", "readonly")

    response = await client.post(
        "/api/admin/auth/protected-write",
        headers={"Authorization": f"Bearer {token}"},
        json={"test": "data"},
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_superadmin_can_access_write(client: AsyncClient, token_factory):
    """超管可访问写入端点"""
    token = await token_factory("admin1", "superadmin")

    response = await client.post(
        "/api/admin/auth/protected-write",
        headers={"Authorization": f"Bearer {token}"},
        json={"test": "data"},
    )
    assert response.status_code == 201


@pytest.mark.asyncio
async def test_dept_admin_can_access_write(client: AsyncClient, token_factory):
    """部门管理员可访问写入端点"""
    token = await token_factory("deptadmin1", "dept_admin")

    response = await client.post(
        "/api/admin/auth/protected-write",
        headers={"Authorization": f"Bearer {token}"},
        json={"test": "data"},
    )
    assert response.status_code == 201
