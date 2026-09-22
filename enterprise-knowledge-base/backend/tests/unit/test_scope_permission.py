"""B1 — scope_permission 动态权限表测试

验证:
  - CRUD API: 创建/列表/更新/删除权限
  - 动态加载: map_role_to_scopes 从 DB 读取而非硬编码
  - 缓存刷新: 权限变更后即时生效
  - 默认回退: DB 为空时使用内置默认值
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


class TestScopePermissionAPI:
    """API 端点 — CRUD 操作"""

    @pytest.mark.asyncio
    async def test_create_permission(self, client, token_factory):
        token = await token_factory("sp_admin", "superadmin", None, "SpAdmin1!")
        headers = {"Authorization": f"Bearer {token}"}

        resp = await client.post("/api/admin/scope-permissions", headers=headers, json={
            "role": "operator", "scope": "customer", "is_active": True,
        })
        assert resp.status_code == 201
        data = resp.json()
        assert data["role"] == "operator"
        assert data["scope"] == "customer"

    @pytest.mark.asyncio
    async def test_list_permissions(self, client, token_factory):
        token = await token_factory("sp_list", "superadmin", None, "SpList1!")
        headers = {"Authorization": f"Bearer {token}"}

        await client.post("/api/admin/scope-permissions", headers=headers, json={
            "role": "readonly", "scope": "customer",
        })
        resp = await client.get("/api/admin/scope-permissions", headers=headers)
        assert resp.status_code == 200
        items = resp.json()
        assert len(items) >= 1

    @pytest.mark.asyncio
    async def test_update_permission(self, client, token_factory):
        token = await token_factory("sp_upd", "superadmin", None, "SpUpdate1!")
        headers = {"Authorization": f"Bearer {token}"}

        resp = await client.post("/api/admin/scope-permissions", headers=headers, json={
            "role": "dept_admin", "scope": "internal",
        })
        perm_id = resp.json()["id"]

        resp = await client.put(f"/api/admin/scope-permissions/{perm_id}", headers=headers, json={
            "is_active": False,
        })
        assert resp.status_code == 200
        assert resp.json()["is_active"] is False

    @pytest.mark.asyncio
    async def test_delete_permission(self, client, token_factory):
        token = await token_factory("sp_del", "superadmin", None, "SpDelete1!")
        headers = {"Authorization": f"Bearer {token}"}

        resp = await client.post("/api/admin/scope-permissions", headers=headers, json={
            "role": "readonly", "scope": "internal",
        })
        perm_id = resp.json()["id"]

        resp = await client.delete(f"/api/admin/scope-permissions/{perm_id}", headers=headers)
        assert resp.status_code == 204

    @pytest.mark.asyncio
    async def test_bulk_create_default_permissions(self, client, token_factory):
        token = await token_factory("sp_bulk", "superadmin", None, "SpBulk1!")
        headers = {"Authorization": f"Bearer {token}"}

        resp = await client.post("/api/admin/scope-permissions/defaults", headers=headers)
        assert resp.status_code == 201
        data = resp.json()
        assert data["created"] >= 4

    @pytest.mark.asyncio
    async def test_reload_permission_cache(self, client, token_factory):
        token = await token_factory("sp_reload", "superadmin", None, "SpReload1!")
        headers = {"Authorization": f"Bearer {token}"}

        await client.post("/api/admin/scope-permissions/defaults", headers=headers)

        resp = await client.post("/api/admin/scope-permissions/reload", headers=headers)
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

    @pytest.mark.asyncio
    async def test_readonly_cannot_create_permission(self, client):
        await client.post("/api/admin/auth/register", json={
            "username": "sp_ro_b1", "password": "SpReadOnly1!",
            "password_confirm": "SpReadOnly1!", "display_name": "SP RO",
            "role": "readonly",
        })
        resp = await client.post("/api/admin/auth/login", data={
            "username": "sp_ro_b1", "password": "SpReadOnly1!",
        })
        token = resp.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        resp = await client.post("/api/admin/scope-permissions", headers=headers, json={
            "role": "operator", "scope": "customer",
        })
        assert resp.status_code == 403


class TestMapRoleToScopesDynamic:
    """动态权限映射 — 从 DB 读取"""

    @pytest.mark.asyncio
    async def test_returns_defaults_when_db_empty(self, db_session):
        from app.agents.nodes.auth import map_role_to_scopes

        scopes = await map_role_to_scopes(db_session, "superadmin")
        assert "public" in scopes
        assert "internal" in scopes
        assert "customer" in scopes

    @pytest.mark.asyncio
    async def test_returns_from_db_when_populated(self, db_session):
        from app.models.scope_permission import ScopePermission
        from app.agents.nodes.auth import map_role_to_scopes

        db_session.add(ScopePermission(role="readonly", scope="customer", is_active=True))
        db_session.add(ScopePermission(role="readonly", scope="public", is_active=True))
        await db_session.commit()

        scopes = await map_role_to_scopes(db_session, "readonly")
        assert "customer" in scopes
        assert "public" in scopes

    @pytest.mark.asyncio
    async def test_inactive_permissions_excluded(self, db_session):
        from app.models.scope_permission import ScopePermission
        from app.agents.nodes.auth import map_role_to_scopes

        db_session.add(ScopePermission(role="readonly", scope="customer", is_active=False))
        await db_session.commit()

        scopes = await map_role_to_scopes(db_session, "readonly")
        assert "customer" not in scopes

    @pytest.mark.asyncio
    async def test_unknown_role_falls_back_to_public(self, db_session):
        from app.agents.nodes.auth import map_role_to_scopes

        scopes = await map_role_to_scopes(db_session, "nonexistent_role")
        assert scopes == ["public"]

    @pytest.mark.asyncio
    async def test_cache_refresh_after_db_change(self, db_session):
        from app.models.scope_permission import ScopePermission
        from app.agents.nodes.auth import (
            map_role_to_scopes,
            refresh_scope_permission_cache,
        )

        scopes = await map_role_to_scopes(db_session, "readonly")
        assert "customer" not in scopes

        db_session.add(ScopePermission(role="readonly", scope="customer", is_active=True))
        await db_session.commit()

        await refresh_scope_permission_cache(db_session)
        scopes = await map_role_to_scopes(db_session, "readonly")
        assert "customer" in scopes
