"""用户注册测试 (TDD: RED)"""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_register_with_valid_data_returns_201(client: AsyncClient):
    """正常注册应返回 201"""
    response = await client.post(
        "/api/admin/auth/register",
        json={
            "username": "zhangsan",
            "password": "SecureP@ss1",
            "password_confirm": "SecureP@ss1",
            "display_name": "张三",
            "email": "zhangsan@example.com",
        },
    )
    assert response.status_code == 201
    data = response.json()
    assert data["username"] == "zhangsan"
    assert data["email"] == "zhangsan@example.com"
    assert data["display_name"] == "张三"
    assert data["role"] == "readonly"
    assert data["is_active"] is True
    assert "id" in data


@pytest.mark.asyncio
async def test_register_duplicate_username_returns_400(client: AsyncClient):
    """重复用户名注册应返回 400"""
    payload = {
        "username": "lisi",
        "password": "SecureP@ss1",
        "password_confirm": "SecureP@ss1",
        "display_name": "李四",
        "email": "lisi@example.com",
    }
    resp1 = await client.post("/api/admin/auth/register", json=payload)
    assert resp1.status_code == 201

    resp2 = await client.post("/api/admin/auth/register", json=payload)
    assert resp2.status_code == 400


@pytest.mark.asyncio
async def test_register_missing_username_returns_422(client: AsyncClient):
    """缺少用户名应返回 422"""
    response = await client.post(
        "/api/admin/auth/register",
        json={"password": "SecureP@ss1", "password_confirm": "SecureP@ss1"},
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_register_weak_password_returns_422(client: AsyncClient):
    """弱密码（<8 位）应返回 422"""
    response = await client.post(
        "/api/admin/auth/register",
        json={
            "username": "wangwu",
            "password": "123",
            "password_confirm": "123",
        },
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_register_password_mismatch_returns_422(client: AsyncClient):
    """两次密码不一致应返回 422"""
    response = await client.post(
        "/api/admin/auth/register",
        json={
            "username": "zhaoliu",
            "password": "SecureP@ss1",
            "password_confirm": "DifferentP@ss1",
        },
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_register_invalid_role_returns_422(client: AsyncClient):
    """非法角色应返回 422（只允许 superadmin/dept_admin/operator/readonly）"""
    response = await client.post(
        "/api/admin/auth/register",
        json={
            "username": "hacker",
            "password": "SecureP@ss1",
            "password_confirm": "SecureP@ss1",
            "role": "root",
        },
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_register_invalid_email_returns_422(client: AsyncClient):
    """非法邮箱格式应返回 422"""
    response = await client.post(
        "/api/admin/auth/register",
        json={
            "username": "testuser",
            "password": "SecureP@ss1",
            "password_confirm": "SecureP@ss1",
            "email": "not-an-email",
        },
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_register_cannot_escalate_role(client: AsyncClient):
    """安全回归：公开注册即使携带高权限角色，也强制落库为 readonly，杜绝提权"""
    response = await client.post(
        "/api/admin/auth/register",
        json={
            "username": "escalate1",
            "password": "SecureP@ss1",
            "password_confirm": "SecureP@ss1",
            "role": "superadmin",
        },
    )
    assert response.status_code == 201
    assert response.json()["role"] == "readonly"
