"""集成测试 — 未命中问题流程：提交 → 列表 → 状态更新 → LLM 转 FAQ"""

import pytest
from unittest.mock import MagicMock, patch


class TestUnansweredFlow:
    async def _login(self, client, token_factory, username="ua_flow_1", password="UaFlow1!"):
        return await token_factory(username, "superadmin", password=password)

    @pytest.mark.asyncio
    async def test_submit_list_and_update_unanswered(self, client, token_factory):
        token = await self._login(client, token_factory)
        headers = {"Authorization": f"Bearer {token}"}

        resp = await client.post("/api/admin/unanswered", headers=headers, json={
            "thread_id": "ua_thread_001",
            "question": "如何申请远程办公？",
            "source": "customer",
        })
        assert resp.status_code == 201

        resp = await client.get("/api/admin/unanswered", headers=headers)
        assert resp.status_code == 200
        items = resp.json()
        assert len(items) >= 1
        ua_id = items[0]["id"]

        resp = await client.patch(
            f"/api/admin/unanswered/{ua_id}",
            headers=headers,
            json={"status": "ignored"},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "ignored"

    @pytest.mark.asyncio
    async def test_convert_unanswered_to_faq(self, client, token_factory):
        mock_llm = MagicMock()
        mock_resp = MagicMock()
        mock_resp.content = "远程办公申请流程：员工需在OA系统提交远程办公申请表，经直属领导审批后生效。"
        mock_llm.ainvoke = MagicMock(return_value=mock_resp)

        token = await self._login(client, token_factory)
        headers = {"Authorization": f"Bearer {token}"}

        resp = await client.post("/api/admin/unanswered", headers=headers, json={
            "thread_id": "ua_convert_001",
            "question": "怎么样进行线上请假？",
            "source": "customer",
        })
        assert resp.status_code == 201
        ua_id = resp.json()["id"]

        with patch("app.agents.llm.create_llm", return_value=mock_llm):
            resp = await client.post(
                f"/api/admin/unanswered/{ua_id}/convert",
                headers=headers,
            )
            assert resp.status_code == 200
            data = resp.json()
            assert data["faq_id"] > 0
            assert "generated_answer" in data

    @pytest.mark.asyncio
    async def test_unanswered_filter_by_status(self, client, token_factory):
        token = await self._login(client, token_factory)
        headers = {"Authorization": f"Bearer {token}"}

        resp = await client.get("/api/admin/unanswered?status=pending", headers=headers)
        assert resp.status_code == 200
        items = resp.json()
        for item in items:
            assert item["status"] == "pending"
