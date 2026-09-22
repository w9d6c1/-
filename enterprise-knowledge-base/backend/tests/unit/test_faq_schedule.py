"""FAQ 定时上下架 测试"""

from datetime import datetime, timedelta, timezone

import pytest
from httpx import AsyncClient


class TestEffectiveTimeFilter:
    @pytest.mark.asyncio
    async def test_create_with_effective_start(self, client: AsyncClient, token_factory):
        token = await token_factory("eff_start_op", "operator")
        future_time = (datetime.now(timezone.utc) + timedelta(days=7)).strftime("%Y-%m-%d %H:%M:%S")

        resp = await client.post("/api/admin/faqs", json={
            "category_id": 1,
            "question": "定时上线 FAQ",
            "answer": "定时测试",
            "scope": "public",
            "effective_start": future_time,
        }, headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 201
        assert resp.json()["effective_start"] is not None

    @pytest.mark.asyncio
    async def test_create_with_effective_end(self, client: AsyncClient, token_factory):
        token = await token_factory("eff_end_op", "operator")
        future_time = (datetime.now(timezone.utc) + timedelta(days=14)).strftime("%Y-%m-%d %H:%M:%S")

        resp = await client.post("/api/admin/faqs", json={
            "category_id": 1,
            "question": "定时下线 FAQ",
            "answer": "定时测试",
            "scope": "public",
            "effective_end": future_time,
        }, headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 201
        assert resp.json()["effective_end"] is not None

    @pytest.mark.asyncio
    async def test_update_effective_time(self, client: AsyncClient, token_factory):
        token = await token_factory("eff_update_op", "operator")
        start = (datetime.now(timezone.utc) + timedelta(days=1)).strftime("%Y-%m-%d %H:%M:%S")
        end = (datetime.now(timezone.utc) + timedelta(days=30)).strftime("%Y-%m-%d %H:%M:%S")

        resp = await client.post("/api/admin/faqs", json={
            "category_id": 1,
            "question": "更新生效时间 FAQ",
            "answer": "测试",
            "scope": "public",
        }, headers={"Authorization": f"Bearer {token}"})
        faq_id = resp.json()["id"]

        resp2 = await client.put(f"/api/admin/faqs/{faq_id}", json={
            "effective_start": start,
            "effective_end": end,
        }, headers={"Authorization": f"Bearer {token}"})
        assert resp2.status_code == 200
        assert resp2.json()["effective_start"] is not None
        assert resp2.json()["effective_end"] is not None
