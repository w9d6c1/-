"""FAQ 向量自动刷新测试 (TDD: RED)"""

import pytest
from unittest.mock import AsyncMock, patch




async def _reload(client, token: str):
    with patch(
        "app.agents.nodes.faq.embed_texts",
        new=AsyncMock(side_effect=lambda texts: [[0.1] * 1024 for _ in texts]),
    ):
        return await client.post("/api/admin/faqs/reload-vectors", headers={"Authorization": f"Bearer {token}"})


class TestFAQVectorReload:
    @pytest.mark.asyncio
    async def test_vectors_reload_after_create(self, client, db_session, token_factory):
        """新增 FAQ 后手动刷新向量，包含新 FAQ"""
        from app.agents.nodes.faq import get_faq_vectors, _clear_faq_vectors

        await _clear_faq_vectors()

        token = await token_factory("reload_create", role="superadmin")
        resp = await client.post(
            "/api/admin/faqs",
            json={"category_id": 1, "question": "自动刷新测试", "answer": "刷新后的答案", "scope": "public"},
            headers={"Authorization": f"Bearer {token}"},
        )
        faq_id = resp.json()["id"]
        await client.post(f"/api/admin/faqs/{faq_id}/submit", headers={"Authorization": f"Bearer {token}"})
        await client.post(f"/api/admin/faqs/{faq_id}/approve", headers={"Authorization": f"Bearer {token}"})
        # 手动触发刷新
        await _reload(client, token)

        vectors = get_faq_vectors()
        found = [v for v in vectors if v["faq_id"] == faq_id]
        assert len(found) > 0

    @pytest.mark.asyncio
    async def test_vectors_reload_after_update(self, client, db_session, token_factory):
        """修改 FAQ 内容后手动刷新向量，内容更新"""
        from app.agents.nodes.faq import get_faq_vectors, _clear_faq_vectors

        await _clear_faq_vectors()

        token = await token_factory("reload_update", role="superadmin")
        resp = await client.post(
            "/api/admin/faqs",
            json={"category_id": 1, "question": "原问题", "answer": "原答案", "scope": "public"},
            headers={"Authorization": f"Bearer {token}"},
        )
        faq_id = resp.json()["id"]
        await client.post(f"/api/admin/faqs/{faq_id}/submit", headers={"Authorization": f"Bearer {token}"})
        await client.post(f"/api/admin/faqs/{faq_id}/approve", headers={"Authorization": f"Bearer {token}"})
        await client.put(
            f"/api/admin/faqs/{faq_id}",
            json={"answer": "更新后的答案"},
            headers={"Authorization": f"Bearer {token}"},
        )
        await _reload(client, token)

        vectors = get_faq_vectors()
        found = [v for v in vectors if v["faq_id"] == faq_id]
        assert len(found) > 0
        assert found[0]["content"] == "更新后的答案"

    @pytest.mark.asyncio
    async def test_vectors_reload_after_delete(self, client, db_session, token_factory):
        """删除 FAQ 后手动刷新向量，移除该 FAQ"""
        from app.agents.nodes.faq import get_faq_vectors, _clear_faq_vectors

        await _clear_faq_vectors()

        token = await token_factory("reload_delete", role="superadmin")
        resp = await client.post(
            "/api/admin/faqs",
            json={"category_id": 1, "question": "待删除问题", "answer": "待删除答案", "scope": "public"},
            headers={"Authorization": f"Bearer {token}"},
        )
        faq_id = resp.json()["id"]
        await client.post(f"/api/admin/faqs/{faq_id}/submit", headers={"Authorization": f"Bearer {token}"})
        await client.post(f"/api/admin/faqs/{faq_id}/approve", headers={"Authorization": f"Bearer {token}"})
        await client.delete(f"/api/admin/faqs/{faq_id}", headers={"Authorization": f"Bearer {token}"})
        await _reload(client, token)

        vectors = get_faq_vectors()
        found = [v for v in vectors if v["faq_id"] == faq_id]
        assert len(found) == 0

    @pytest.mark.asyncio
    async def test_set_faq_vectors_thread_safe(self):
        """_set_faq_vectors 和 get_faq_vectors 并发调用不崩溃"""
        import asyncio
        from app.agents.nodes.faq import _set_faq_vectors, _clear_faq_vectors, get_faq_vectors

        await _clear_faq_vectors()

        async def writer():
            with patch(
                "app.agents.nodes.faq.embed_texts",
                new=AsyncMock(side_effect=lambda texts: [[0.1] * 1024 for _ in texts]),
            ):
                for i in range(10):
                    await _set_faq_vectors([{
                        "id": i, "question": f"问题{i}", "answer": f"答案{i}",
                        "scope": "public", "questions_for_embedding": [f"问题{i}"],
                    }], scopes=["public"])
                    await asyncio.sleep(0.001)

        async def reader():
            for _ in range(20):
                get_faq_vectors()
                await asyncio.sleep(0.001)

        await asyncio.gather(writer(), reader())
        await _clear_faq_vectors()

    @pytest.mark.asyncio
    async def test_manual_reload_endpoint(self, client, db_session, token_factory):
        """POST /faqs/reload-vectors 返回已加载数量"""
        from app.agents.nodes.faq import _clear_faq_vectors

        await _clear_faq_vectors()

        token = await token_factory("reload_manual", role="superadmin")
        # 创建 online FAQ
        resp = await client.post(
            "/api/admin/faqs",
            json={"category_id": 1, "question": "手动刷新测试", "answer": "手动答案", "scope": "public"},
            headers={"Authorization": f"Bearer {token}"},
        )
        faq_id = resp.json()["id"]
        await client.post(f"/api/admin/faqs/{faq_id}/submit", headers={"Authorization": f"Bearer {token}"})
        await client.post(f"/api/admin/faqs/{faq_id}/approve", headers={"Authorization": f"Bearer {token}"})

        resp = await _reload(client, token)
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["loaded"] > 0
