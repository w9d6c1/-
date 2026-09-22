"""集成测试 — 用户反馈流程：提交 → 查询列表 → 统计"""

import pytest


class TestFeedbackFlow:
    async def _login(self, client):
        await client.post("/api/admin/auth/register", json={
            "username": "fb_flow_1", "password": "FbFlow1!",
            "password_confirm": "FbFlow1!", "display_name": "FB Flow",
            "role": "superadmin",
        })
        resp = await client.post("/api/admin/auth/login", data={
            "username": "fb_flow_1", "password": "FbFlow1!",
        })
        return resp.json()["access_token"]

    @pytest.mark.asyncio
    async def test_submit_feedback_and_list(self, client):
        token = await self._login(client)
        headers = {"Authorization": f"Bearer {token}"}

        resp = await client.post("/api/admin/feedbacks", headers=headers, json={
            "thread_id": "fb_thread_001",
            "rating": "like",
            "suggestion": "回答很准确",
        })
        assert resp.status_code == 201

        resp = await client.post("/api/admin/feedbacks", headers=headers, json={
            "thread_id": "fb_thread_002",
            "rating": "dislike",
            "suggestion": "回答不够详细",
        })
        assert resp.status_code == 201

        resp = await client.get("/api/admin/feedbacks", headers=headers)
        assert resp.status_code == 200
        feedbacks = resp.json()
        assert len(feedbacks) >= 2

    @pytest.mark.asyncio
    async def test_feedback_stats(self, client):
        token = await self._login(client)
        headers = {"Authorization": f"Bearer {token}"}

        resp = await client.get("/api/admin/feedbacks/stats", headers=headers)
        assert resp.status_code == 200
        stats = resp.json()
        assert "total" in stats
        assert "likes" in stats
        assert "dislikes" in stats

    @pytest.mark.asyncio
    async def test_feedback_filter_by_rating(self, client):
        token = await self._login(client)
        headers = {"Authorization": f"Bearer {token}"}

        resp = await client.get("/api/admin/feedbacks?rating=like", headers=headers)
        assert resp.status_code == 200
        items = resp.json()
        for item in items:
            assert item["rating"] == "like"
