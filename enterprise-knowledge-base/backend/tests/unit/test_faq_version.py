"""FAQ 版本历史 & 回滚 测试"""

import pytest
from httpx import AsyncClient


class TestVersionSnapshot:
    @pytest.mark.asyncio
    async def test_update_creates_snapshot(self, client: AsyncClient, token_factory):
        token = await token_factory("snap_op", "operator")

        resp = await client.post("/api/admin/faqs", json={
            "category_id": 1,
            "question": "版本快照 FAQ",
            "answer": "V1 答案",
            "scope": "public",
        }, headers={"Authorization": f"Bearer {token}"})
        faq_id = resp.json()["id"]
        assert resp.json()["version"] == 1

        resp2 = await client.put(f"/api/admin/faqs/{faq_id}", json={
            "answer": "V2 答案",
        }, headers={"Authorization": f"Bearer {token}"})
        assert resp2.status_code == 200
        assert resp2.json()["version"] == 2

        resp3 = await client.get(f"/api/admin/faqs/{faq_id}/versions", headers={"Authorization": f"Bearer {token}"})
        versions = resp3.json()
        assert len(versions) >= 1
        assert versions[0]["version"] == 1
        assert versions[0]["answer"] == "V1 答案"

    @pytest.mark.asyncio
    async def test_rollback_restores_content(self, client: AsyncClient, token_factory):
        token = await token_factory("rollback_op", "operator")

        resp = await client.post("/api/admin/faqs", json={
            "category_id": 1,
            "question": "回滚测试 FAQ",
            "answer": "原始答案",
            "scope": "public",
        }, headers={"Authorization": f"Bearer {token}"})
        faq_id = resp.json()["id"]

        await client.put(f"/api/admin/faqs/{faq_id}", json={
            "answer": "修改后答案",
        }, headers={"Authorization": f"Bearer {token}"})

        versions = await client.get(f"/api/admin/faqs/{faq_id}/versions", headers={"Authorization": f"Bearer {token}"})
        v1_id = versions.json()[0]["id"]

        resp3 = await client.post(f"/api/admin/faqs/{faq_id}/rollback/{v1_id}", headers={"Authorization": f"Bearer {token}"})
        assert resp3.status_code == 200
        assert resp3.json()["answer"] == "原始答案"

    @pytest.mark.asyncio
    async def test_rollback_resets_review_status_to_approved(self, client: AsyncClient, token_factory):
        token = await token_factory("rollback_rv_op", "operator")

        resp = await client.post("/api/admin/faqs", json={
            "category_id": 1,
            "question": "回滚审核测试 FAQ",
            "answer": "原始",
            "scope": "public",
        }, headers={"Authorization": f"Bearer {token}"})
        faq_id = resp.json()["id"]

        await client.put(f"/api/admin/faqs/{faq_id}", json={"answer": "变更"}, headers={"Authorization": f"Bearer {token}"})

        versions = await client.get(f"/api/admin/faqs/{faq_id}/versions", headers={"Authorization": f"Bearer {token}"})
        v1_id = versions.json()[0]["id"]

        resp3 = await client.post(f"/api/admin/faqs/{faq_id}/rollback/{v1_id}", headers={"Authorization": f"Bearer {token}"})
        assert resp3.json()["review_status"] == "approved"

    @pytest.mark.asyncio
    async def test_rollback_increments_version(self, client: AsyncClient, token_factory):
        token = await token_factory("rollback_ver_op", "operator")

        resp = await client.post("/api/admin/faqs", json={
            "category_id": 1,
            "question": "版本递增 FAQ",
            "answer": "V1",
            "scope": "public",
        }, headers={"Authorization": f"Bearer {token}"})
        faq_id = resp.json()["id"]
        assert resp.json()["version"] == 1

        await client.put(f"/api/admin/faqs/{faq_id}", json={"answer": "V2"}, headers={"Authorization": f"Bearer {token}"})

        versions = await client.get(f"/api/admin/faqs/{faq_id}/versions", headers={"Authorization": f"Bearer {token}"})
        v1_id = versions.json()[0]["id"]

        resp3 = await client.post(f"/api/admin/faqs/{faq_id}/rollback/{v1_id}", headers={"Authorization": f"Bearer {token}"})
        assert resp3.json()["version"] == 3

    @pytest.mark.asyncio
    async def test_get_versions_empty(self, client: AsyncClient, token_factory):
        token = await token_factory("ver_empty_op", "operator")

        resp = await client.post("/api/admin/faqs", json={
            "category_id": 1,
            "question": "无历史 FAQ",
            "answer": "答案",
            "scope": "public",
        }, headers={"Authorization": f"Bearer {token}"})
        faq_id = resp.json()["id"]

        resp2 = await client.get(f"/api/admin/faqs/{faq_id}/versions", headers={"Authorization": f"Bearer {token}"})
        assert resp2.status_code == 200
        assert resp2.json() == []
