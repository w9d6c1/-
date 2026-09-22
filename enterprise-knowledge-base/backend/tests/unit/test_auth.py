"""登录 / JWT 测试 (TDD: RED — 登录和Token校验)"""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_login_with_valid_credentials_returns_token(client: AsyncClient):
    """正常登录应返回 access_token"""
    await client.post(
        "/api/admin/auth/register",
        json={
            "username": "testuser",
            "password": "SecureP@ss1",
            "password_confirm": "SecureP@ss1",
        },
    )

    response = await client.post(
        "/api/admin/auth/login",
        data={"username": "testuser", "password": "SecureP@ss1"},
    )
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"


@pytest.mark.asyncio
async def test_login_with_wrong_password_returns_401(client: AsyncClient):
    """错误密码应返回 401"""
    await client.post(
        "/api/admin/auth/register",
        json={
            "username": "testuser",
            "password": "SecureP@ss1",
            "password_confirm": "SecureP@ss1",
        },
    )

    response = await client.post(
        "/api/admin/auth/login",
        data={"username": "testuser", "password": "WrongPass1"},
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_login_with_nonexistent_user_returns_401(client: AsyncClient):
    """不存在的用户应返回 401"""
    response = await client.post(
        "/api/admin/auth/login",
        data={"username": "nobody", "password": "SecureP@ss1"},
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_protected_endpoint_without_token_returns_401(client: AsyncClient):
    """无 Token 访问受保护端点应返回 401"""
    response = await client.get("/api/admin/auth/me")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_protected_endpoint_with_valid_token_returns_user(client: AsyncClient):
    """有效 Token 访问 /me 应返回用户信息"""
    await client.post(
        "/api/admin/auth/register",
        json={
            "username": "testuser",
            "password": "SecureP@ss1",
            "password_confirm": "SecureP@ss1",
        },
    )

    login_resp = await client.post(
        "/api/admin/auth/login",
        data={"username": "testuser", "password": "SecureP@ss1"},
    )
    token = login_resp.json()["access_token"]

    response = await client.get(
        "/api/admin/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    user = response.json()
    assert user["username"] == "testuser"


@pytest.mark.asyncio
async def test_protected_endpoint_with_invalid_token_returns_401(client: AsyncClient):
    """伪造 Token 应返回 401"""
    response = await client.get(
        "/api/admin/auth/me",
        headers={"Authorization": "Bearer fake-token-here"},
    )
    assert response.status_code == 401
