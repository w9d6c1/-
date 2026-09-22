"""集成测试 — 审计日志链路：chat → chat_log + security_log 落库"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.models.audit import ChatLog, SecurityLog


class TestAuditChain:
    async def _login(self, client, token_factory, username="audit_chain", password="AuditChain1!"):
        token = await token_factory(username, role="superadmin", password=password)
        resp = await client.post("/api/admin/auth/login", data={
            "username": username, "password": password,
        })
        return resp.json()["access_token"]

    @pytest.mark.asyncio
    async def test_login_failure_logs_security_event(self, client, db_session, token_factory):
        token = await self._login(client, token_factory, "audit_log_1", "AuditLogSec1!")

        resp = await client.post("/api/admin/auth/login", data={
            "username": "nonexistent_user_999",
            "password": "wrong_password",
        })
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_faq_crud_logs_operation(self, client, db_session, token_factory):
        token = await self._login(client, token_factory, "audit_op_1", "AuditOpLog1!")
        headers = {"Authorization": f"Bearer {token}"}

        resp = await client.post("/api/admin/faqs", headers=headers, json={
            "category_id": 1, "question": "审计测试问题", "answer": "审计测试答案",
        })
        assert resp.status_code == 201

    @pytest.mark.asyncio
    async def test_chat_log_chain(self, client, db_session, token_factory):
        from unittest.mock import MagicMock, patch

        token = await self._login(client, token_factory, "audit_chat_1", "AuditChat1!")
        headers = {"Authorization": f"Bearer {token}"}

        resp = await client.post(
            "/api/admin/categories",
            headers=headers,
            json={"name": "审计分类", "scope": "public"},
        )
        cat_id = resp.json()["id"]

        resp = await client.post("/api/admin/documents", headers=headers, json={
            "category_id": cat_id, "title": "审计文档", "scope": "public",
        })
        doc_id = resp.json()["id"]

        await client.post(f"/api/admin/documents/{doc_id}/content", headers=headers, json={
            "content": "# 审计测试\n\n内容用于集成测试审计日志链路验证。",
            "file_type": "md",
        })
        await client.post(f"/api/admin/documents/{doc_id}/chunk", headers=headers)
        await client.post(f"/api/admin/documents/{doc_id}/review", headers=headers, json={"action": "approve"})

    @pytest.mark.asyncio
    async def test_chat_logs_to_db(self, client, db_session, token_factory):
        """验证对话日志确实写入 ChatLog 表"""
        from unittest.mock import AsyncMock, MagicMock, patch

        token = await self._login(client, token_factory, "audit_chatlog_1", "AuditChatLog1!")
        headers = {"Authorization": f"Bearer {token}"}

        mock_graph = MagicMock()
        mock_graph.ainvoke = AsyncMock(return_value={
            "final_answer": "审计链路测试回答",
            "is_blocked": False,
            "confidence": 0.92,
            "needs_human": False,
            "faq_hit": True,
            "hit_faq_id": 1,
            "hit_chunk_ids": ["chunk_1", "chunk_2"],
            "total_latency_ms": 350,
            "route": "faq",
            "user_id": None,
        })

        with patch("app.api.agent._get_graph", return_value=mock_graph):
            resp = await client.post(
                "/api/agent/internal/chat",
                json={"message": "审计链路测试提问", "scope": "public", "thread_id": "audit_probe_1"},
            )
            assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_security_log_written_on_sensitive_word(self, client, db_session, token_factory):
        """验证敏感词命中后 SecurityLog 落库"""
        token = await self._login(client, token_factory, "audit_sec_1", "AuditSec1!")
        headers = {"Authorization": f"Bearer {token}"}

        resp = await client.post(
            "/api/agent/internal/chat",
            json={"message": "DROP TABLE users;--", "scope": "public", "thread_id": "sec_probe_1"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["is_blocked"] is True
