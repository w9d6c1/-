"""安全测试 — 认证/授权/注入/安全头"""

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import create_app


@pytest.fixture
async def raw_client():
    """无 DB override 的客户端，用于测试 401 拒绝行为"""
    app = create_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac


class TestUnauthenticatedAccess:
    """未认证请求应返回 401"""

    @pytest.mark.asyncio
    async def test_admin_endpoints_require_auth(self, raw_client):
        endpoints = [
            ("GET", "/api/admin/categories"),
            ("GET", "/api/admin/faqs"),
            ("GET", "/api/admin/documents"),
            ("GET", "/api/admin/feedbacks"),
            ("GET", "/api/admin/unanswered"),
            ("GET", "/api/admin/dashboard/stats"),
        ]
        for method, url in endpoints:
            resp = await raw_client.request(method, url)
            assert resp.status_code == 401, f"{method} {url} should require auth, got {resp.status_code}"

    @pytest.mark.asyncio
    async def test_write_endpoints_require_auth(self, raw_client):
        write_endpoints = [
            ("POST", "/api/admin/faqs", {"category_id": 1, "question": "x", "answer": "y"}),
            ("POST", "/api/admin/categories", {"name": "test", "scope": "public"}),
            ("POST", "/api/admin/synonyms", {"word": "x", "synonyms": ["y"]}),
        ]
        for method, url, body in write_endpoints:
            resp = await raw_client.request(method, url, json=body)
            assert resp.status_code in (401, 422), f"{method} {url} should require auth, got {resp.status_code}"


class TestAuthorization:
    """权限不足应返回 403"""

    @pytest.mark.asyncio
    async def test_readonly_cannot_create_faq(self, client, token_factory):
        token = await token_factory("ro_cfaq_1", "readonly", "测试部", "ReadOnlyAbc1!")
        headers = {"Authorization": f"Bearer {token}"}
        resp = await client.post("/api/admin/faqs", headers=headers, json={
            "category_id": 1, "question": "test", "answer": "test answer",
        })
        assert resp.status_code == 403, f"Readonly should not create FAQ, got {resp.status_code}"

    @pytest.mark.asyncio
    async def test_readonly_cannot_delete_faq(self, client, token_factory):
        token = await token_factory("ro_del_1", "readonly", "测试部", "ReadOnlyAbc2!")
        headers = {"Authorization": f"Bearer {token}"}
        resp = await client.delete("/api/admin/faqs/1", headers=headers)
        assert resp.status_code == 403, f"Readonly should not delete, got {resp.status_code}"

    @pytest.mark.asyncio
    async def test_readonly_can_view_list(self, client, token_factory):
        token = await token_factory("ro_view_1", "readonly", "测试部", "ReadOnlyAbc3!")
        headers = {"Authorization": f"Bearer {token}"}
        resp = await client.get("/api/admin/faqs", headers=headers)
        assert resp.status_code == 200, f"Readonly should view list, got {resp.status_code}"

    @pytest.mark.asyncio
    async def test_auth_me_returns_correct_user(self, client, token_factory):
        token = await token_factory("me_test_1", "operator", "测试部", "MeTestAbc1!")
        headers = {"Authorization": f"Bearer {token}"}
        resp = await client.get("/api/admin/auth/me", headers=headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["role"] == "operator"


class TestJWTValidation:
    """JWT 令牌安全校验"""

    @pytest.mark.asyncio
    async def test_invalid_token_rejected(self, raw_client):
        headers = {"Authorization": "Bearer invalid_token_12345"}
        resp = await raw_client.get("/api/admin/auth/me", headers=headers)
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_missing_token_rejected(self, raw_client):
        resp = await raw_client.get("/api/admin/auth/me")
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_none_algorithm_rejected(self, raw_client):
        headers = {"Authorization": "Bearer eyJhbGciOiJub25lIiwidHlwIjoiSldUIn0.eyJzdWIiOiJ0ZXN0In0."}
        resp = await raw_client.get("/api/admin/auth/me", headers=headers)
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_expired_token_rejected(self, raw_client):
        headers = {"Authorization": "Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxIiwiZXhwIjoxMDAwMDAwMDAwfQ.INVALID_SIGNATURE"}
        resp = await raw_client.get("/api/admin/auth/me", headers=headers)
        assert resp.status_code == 401


class TestInputValidation:
    """输入校验防注入"""

    @pytest.mark.asyncio
    async def test_sql_injection_in_login_rejected(self, client):
        resp = await client.post("/api/admin/auth/login", data={
            "username": "admin' OR '1'='1",
            "password": "' OR '1'='1",
        })
        assert resp.status_code in (401, 422), f"SQL injection should fail, got {resp.status_code}"

    @pytest.mark.asyncio
    async def test_empty_username_rejected(self, raw_client):
        resp = await raw_client.post("/api/admin/auth/login", data={
            "username": "", "password": "test",
        })
        assert resp.status_code in (401, 422)

    @pytest.mark.asyncio
    async def test_missing_fields_rejected(self, raw_client):
        resp = await raw_client.post("/api/admin/auth/login", data={})
        assert resp.status_code == 422


class TestSecurityHeaders:
    """安全头与错误处理"""

    @pytest.mark.asyncio
    async def test_error_no_stack_trace(self, raw_client):
        resp = await raw_client.get("/api/nonexistent")
        body = resp.text.lower()
        assert "traceback" not in body
        assert 'file "' not in body
