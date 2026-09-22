"""集成测试 — 仪表盘统计聚合 + 词库管理 + 管理员 info"""

import pytest


class TestDashboardFlow:
    async def _login(self, client, token_factory, username="dashboard_int", password="DashInt1!"):
        return await token_factory(username, "superadmin", password=password)

    @pytest.mark.asyncio
    async def test_dashboard_stats_empty(self, client, token_factory):
        token = await self._login(client, token_factory)
        headers = {"Authorization": f"Bearer {token}"}

        resp = await client.get("/api/admin/dashboard/stats", headers=headers)
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
    async def test_admin_status_endpoint(self, client, token_factory):
        token = await self._login(client, token_factory)
        headers = {"Authorization": f"Bearer {token}"}

        resp = await client.get("/api/admin/status", headers=headers)
        assert resp.status_code == 200
        assert resp.json()["module"] == "admin"


class TestDictionaryFlow:
    async def _login(self, client, token_factory, username="dict_int_1", password="DictInt1!"):
        return await token_factory(username, "superadmin", password=password)

    @pytest.mark.asyncio
    async def test_synonym_crud_flow(self, client, token_factory):
        token = await self._login(client, token_factory)
        headers = {"Authorization": f"Bearer {token}"}

        resp = await client.post("/api/admin/synonyms", headers=headers, json={
            "word": "远程办公",
            "synonyms": ["居家办公", "远程工作", "WFH"],
            "scope": "public",
        })
        assert resp.status_code == 201
        syn_id = resp.json()["id"]

        resp = await client.get("/api/admin/synonyms", headers=headers)
        assert resp.status_code == 200
        items = resp.json()
        assert len(items) >= 1

        resp = await client.delete(f"/api/admin/synonyms/{syn_id}", headers=headers)
        assert resp.status_code == 204

    @pytest.mark.asyncio
    async def test_sensitive_word_crud_flow(self, client, token_factory):
        token = await self._login(client, token_factory)
        headers = {"Authorization": f"Bearer {token}"}

        resp = await client.post("/api/admin/sensitive-words", headers=headers, json={
            "word": "敏感测试词", "word_type": "sensitive",
        })
        assert resp.status_code == 201
        sw_id = resp.json()["id"]

        resp = await client.get("/api/admin/sensitive-words", headers=headers)
        assert resp.status_code == 200

        resp = await client.delete(f"/api/admin/sensitive-words/{sw_id}", headers=headers)
        assert resp.status_code == 204
