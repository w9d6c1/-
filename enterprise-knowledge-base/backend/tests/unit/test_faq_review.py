"""FAQ 审核流程 测试"""

import pytest
from httpx import AsyncClient


FAQ_CREATE = {
    "category_id": 1,
    "question": "审核测试 FAQ",
    "answer": "测试答案内容",
    "scope": "public",
}


class TestReviewWorkflow:
    @pytest.mark.asyncio
    async def test_submit_draft_to_pending(self, client: AsyncClient, token_factory):
        token = await token_factory("reviewer1", "operator")
        resp = await client.post("/api/admin/faqs", json=FAQ_CREATE, headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 201
        faq_id = resp.json()["id"]
        assert resp.json()["review_status"] == "pending"
        assert resp.json()["status"] == "draft"

        resp2 = await client.post(f"/api/admin/faqs/{faq_id}/submit", headers={"Authorization": f"Bearer {token}"})
        assert resp2.status_code == 200

    @pytest.mark.asyncio
    async def test_approve_pending_to_online(self, client: AsyncClient, token_factory):
        op_token = await token_factory("review_op", "operator")
        admin_token = await token_factory("review_admin", "superadmin")

        resp = await client.post("/api/admin/faqs", json=FAQ_CREATE, headers={"Authorization": f"Bearer {op_token}"})
        faq_id = resp.json()["id"]

        resp2 = await client.post(f"/api/admin/faqs/{faq_id}/submit", headers={"Authorization": f"Bearer {op_token}"})
        assert resp2.status_code == 200

        resp3 = await client.post(f"/api/admin/faqs/{faq_id}/approve", headers={"Authorization": f"Bearer {admin_token}"})
        assert resp3.status_code == 200
        data = resp3.json()
        assert data["review_status"] == "approved"
        assert data["status"] == "online"

    @pytest.mark.asyncio
    async def test_reject_pending_to_draft(self, client: AsyncClient, token_factory):
        op_token = await token_factory("reject_op", "operator")
        admin_token = await token_factory("reject_admin", "dept_admin")

        resp = await client.post("/api/admin/faqs", json=FAQ_CREATE, headers={"Authorization": f"Bearer {op_token}"})
        faq_id = resp.json()["id"]

        await client.post(f"/api/admin/faqs/{faq_id}/submit", headers={"Authorization": f"Bearer {op_token}"})

        resp3 = await client.post(f"/api/admin/faqs/{faq_id}/reject", json={"action": "reject"}, headers={"Authorization": f"Bearer {admin_token}"})
        assert resp3.status_code == 200
        data = resp3.json()
        assert data["review_status"] == "rejected"
        assert data["status"] == "draft"

    @pytest.mark.asyncio
    async def test_approve_not_pending_returns_400(self, client: AsyncClient, token_factory):
        op_token = await token_factory("bad_approve_op", "operator")
        admin_token = await token_factory("bad_approve_admin", "superadmin")

        resp = await client.post("/api/admin/faqs", json=FAQ_CREATE, headers={"Authorization": f"Bearer {op_token}"})
        faq_id = resp.json()["id"]

        await client.post(f"/api/admin/faqs/{faq_id}/submit", headers={"Authorization": f"Bearer {op_token}"})
        await client.post(f"/api/admin/faqs/{faq_id}/approve", headers={"Authorization": f"Bearer {admin_token}"})

        resp2 = await client.post(f"/api/admin/faqs/{faq_id}/approve", headers={"Authorization": f"Bearer {admin_token}"})
        assert resp2.status_code == 400

    @pytest.mark.asyncio
    async def test_readonly_cannot_approve(self, client: AsyncClient, token_factory):
        op_token = await token_factory("perm_op", "operator")
        ro_token = await token_factory("perm_ro", "readonly")

        resp = await client.post("/api/admin/faqs", json=FAQ_CREATE, headers={"Authorization": f"Bearer {op_token}"})
        faq_id = resp.json()["id"]

        await client.post(f"/api/admin/faqs/{faq_id}/submit", headers={"Authorization": f"Bearer {op_token}"})

        resp2 = await client.post(f"/api/admin/faqs/{faq_id}/approve", headers={"Authorization": f"Bearer {ro_token}"})
        assert resp2.status_code == 403

    @pytest.mark.asyncio
    async def test_approve_sets_reviewer_id(self, client: AsyncClient, token_factory):
        op_token = await token_factory("set_rev_op", "operator")
        admin_token = await token_factory("set_rev_admin", "superadmin")

        resp = await client.post("/api/admin/faqs", json=FAQ_CREATE, headers={"Authorization": f"Bearer {op_token}"})
        faq_id = resp.json()["id"]

        await client.post(f"/api/admin/faqs/{faq_id}/submit", headers={"Authorization": f"Bearer {op_token}"})

        resp3 = await client.post(f"/api/admin/faqs/{faq_id}/approve", headers={"Authorization": f"Bearer {admin_token}"})
        assert resp3.json()["reviewer_id"] is not None
