"""集成测试 — 认证流程：注册 → 登录 → token 验证 → me 接口"""

import pytest


class TestAuthFlow:
    @pytest.mark.asyncio
    async def test_register_login_get_me_chain(self, client):
        resp = await client.post("/api/admin/auth/register", json={
            "username": "int_auth_flow",
            "password": "IntAuthFlow1!",
            "password_confirm": "IntAuthFlow1!",
            "display_name": "集成测试用户",
            "role": "operator",
        })
        assert resp.status_code == 201
        user = resp.json()
        assert user["role"] == "readonly"  # register 强制 readonly（安全设计）

        resp = await client.post("/api/admin/auth/login", data={
            "username": "int_auth_flow",
            "password": "IntAuthFlow1!",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "access_token" in data
        token = data["access_token"]

        headers = {"Authorization": f"Bearer {token}"}
        resp = await client.get("/api/admin/auth/me", headers=headers)
        assert resp.status_code == 200
        me = resp.json()
        assert me["username"] == "int_auth_flow"
        assert me["role"] == "readonly"

    @pytest.mark.asyncio
    async def test_register_duplicate_rejected(self, client):
        resp = await client.post("/api/admin/auth/register", json={
            "username": "dup_user_1",
            "password": "DupUserPass1!",
            "password_confirm": "DupUserPass1!",
            "display_name": "Dup User",
        })
        assert resp.status_code == 201

        resp = await client.post("/api/admin/auth/register", json={
            "username": "dup_user_1",
            "password": "AnotherPass1!",
            "password_confirm": "AnotherPass1!",
            "display_name": "Dup User 2",
        })
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_register_defaults_readonly(self, client):
        resp = await client.post("/api/admin/auth/register", json={
            "username": "default_role",
            "password": "DefaultRole1!",
            "password_confirm": "DefaultRole1!",
            "display_name": "Default Role User",
        })
        assert resp.status_code == 201
        assert resp.json()["role"] == "readonly"
