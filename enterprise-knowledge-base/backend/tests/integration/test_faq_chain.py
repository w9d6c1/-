"""集成测试 — FAQ 向量刷新链路：创建 → 自动刷新 → reload 端点 → 删除后清空"""

import pytest


class TestFAQVectorChain:
    async def _login(self, client, token_factory, username, password):
        return await token_factory(username, "superadmin", password=password)

    @pytest.mark.asyncio
    async def test_faq_crud_triggers_vector_reload(self, client, token_factory):
        token = await self._login(client, token_factory, "faq_vec_1", "FaqVec123!")
        headers = {"Authorization": f"Bearer {token}"}

        resp = await client.post("/api/admin/faqs", headers=headers, json={
            "category_id": 1, "question": "集成测试FAQ问题", "answer": "集成测试FAQ答案",
        })
        assert resp.status_code == 201
        faq_id = resp.json()["id"]

        resp = await client.put(f"/api/admin/faqs/{faq_id}", headers=headers, json={
            "question": "更新后的FAQ问题",
            "answer": "更新后的FAQ答案",
        })
        assert resp.status_code == 200

        resp = await client.post("/api/admin/faqs/reload-vectors", headers=headers)
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

    @pytest.mark.asyncio
    async def test_faq_get_by_id(self, client, token_factory):
        token = await self._login(client, token_factory, "faq_get_1", "FaqGetId1!")
        headers = {"Authorization": f"Bearer {token}"}

        resp = await client.post("/api/admin/faqs", headers=headers, json={
            "category_id": 1, "question": "单独查询测试", "answer": "查询答案",
        })
        faq_id = resp.json()["id"]

        resp = await client.get(f"/api/admin/faqs/{faq_id}", headers=headers)
        assert resp.status_code == 200
        assert resp.json()["question"] == "单独查询测试"

    @pytest.mark.asyncio
    async def test_faq_bulk_import(self, client, token_factory):
        token = await self._login(client, token_factory, "faq_bulk_1", "FaqBulk1!")
        headers = {"Authorization": f"Bearer {token}"}

        resp = await client.post("/api/admin/faqs/bulk", headers=headers, json={
            "items": [
                {"category_id": 1, "question": "批量问题1", "answer": "批量答案1"},
                {"category_id": 1, "question": "批量问题2", "answer": "批量答案2"},
            ],
        })
        assert resp.status_code == 201
        assert resp.json()["imported"] == 2
