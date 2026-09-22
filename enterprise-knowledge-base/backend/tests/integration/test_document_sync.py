"""集成测试 — 文档审批与自动同步链路"""

import pytest


class TestDocumentApproveSync:
    async def _login(self, client, token_factory, username="doc_sync_1", password="DocSync1!"):
        return await token_factory(username, "superadmin", password=password)

    @pytest.mark.asyncio
    async def test_document_create_upload_chunk_approve(self, client, token_factory):
        token = await self._login(client, token_factory)
        headers = {"Authorization": f"Bearer {token}"}

        resp = await client.post(
            "/api/admin/categories",
            headers=headers,
            json={"name": "同步测试分类", "scope": "public"},
        )
        assert resp.status_code == 201
        cat_id = resp.json()["id"]

        resp = await client.post("/api/admin/documents", headers=headers, json={
            "category_id": cat_id, "title": "文档集成测试", "scope": "public",
            "chunk_strategy": "recursive", "chunk_size": 500, "chunk_overlap": 100,
        })
        assert resp.status_code == 201
        doc = resp.json()
        assert doc["title"] == "文档集成测试"
        doc_id = doc["id"]

        content = """# 公司福利制度

## 年假
工作满1年享受5天带薪年假，每年增加1天，上限15天。

## 补贴
餐补每天30元，交通补贴每月200元。
"""
        resp = await client.post(f"/api/admin/documents/{doc_id}/content", headers=headers, json={
            "content": content, "file_type": "md",
        })
        assert resp.status_code == 200
        assert resp.json()["word_count"] > 0

        resp = await client.post(f"/api/admin/documents/{doc_id}/chunk", headers=headers)
        assert resp.status_code == 200
        assert resp.json()["chunk_count"] > 0

        resp = await client.post(f"/api/admin/documents/{doc_id}/review", headers=headers, json={
            "action": "approve",
        })
        assert resp.status_code == 200
        doc = resp.json()
        assert doc["review_status"] == "approved"
        assert doc["status"] == "online"

    @pytest.mark.asyncio
    async def test_document_review_reject(self, client, token_factory):
        token = await self._login(client, token_factory)
        headers = {"Authorization": f"Bearer {token}"}

        resp = await client.post("/api/admin/documents", headers=headers, json={
            "category_id": 1, "title": "驳回测试文档", "scope": "public",
        })
        doc_id = resp.json()["id"]

        resp = await client.post(f"/api/admin/documents/{doc_id}/review", headers=headers, json={
            "action": "reject",
        })
        assert resp.status_code == 200
        assert resp.json()["review_status"] == "rejected"
        assert resp.json()["status"] == "draft"
