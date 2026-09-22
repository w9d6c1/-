"""E2E: 超级管理员创建 → 文档上传 → 分块 → 审核 → 同步 → AI 问答"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from httpx import AsyncClient

SUPERADMIN = {
    "username": "e2e_admin",
    "password": "E2eTest123!",
    "password_confirm": "E2eTest123!",
    "display_name": "E2E 管理员",
    "role": "superadmin",
    "department": "技术部",
}

DOC_CONTENT = """# 企业考勤管理制度

## 第一条 总则
为规范公司考勤管理，保障正常的工作秩序，特制定本制度。

## 第二条 工作时间
公司实行每周五天工作制，标准工作时间为：
- 上午：09:00 — 12:00
- 下午：13:30 — 18:00
- 弹性打卡：允许 ±30 分钟弹性时间

## 第三条 请假制度
员工请假需提前一天在 OA 系统提交申请：
- 年假：工作满 1 年可享受 5 天带薪年假
- 病假：需提供医院证明，每月不超过 3 天
- 事假：无薪，每月不超过 2 天

## 第四条 加班管理
加班需经直属领导审批，工作日加班按 1.5 倍工资计算，休息日加班按 2 倍计算。
"""


async def _register_superadmin_via_token_factory(token_factory) -> str:
    """通过 token_factory 直接创建 superadmin（绕过注册接口的 readonly 限制）"""
    return await token_factory(
        SUPERADMIN["username"], role="superadmin",
        department=SUPERADMIN.get("department"),
        password=SUPERADMIN["password"],
    )


async def _login(client: AsyncClient) -> str:
    resp = await client.post(
        "/api/admin/auth/login",
        data={"username": SUPERADMIN["username"], "password": SUPERADMIN["password"]},
    )
    assert resp.status_code == 200, f"登录失败: {resp.text}"
    return resp.json()["access_token"]


def _auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


class TestE2EFullPipeline:
    @pytest.mark.asyncio
    async def test_register_and_login(self, client: AsyncClient, token_factory):
        """测试用户注册(默认 readonly)和登录"""
        resp = await client.post("/api/admin/auth/register", json=SUPERADMIN)
        assert resp.status_code == 201, f"注册失败: {resp.text}"
        user = resp.json()
        assert user["role"] == "readonly", "注册接口强制 readonly (安全设计)"
        assert user["username"] == SUPERADMIN["username"]

        token = await _login(client)
        assert len(token) > 0

        resp = await client.get("/api/admin/auth/me", headers=_auth_headers(token))
        assert resp.status_code == 200
        assert resp.json()["role"] == "readonly"

        admin_token = await token_factory(
            "e2e_superadmin", role="superadmin",
            department="技术部", password="E2eAdminPass123!",
        )
        assert len(admin_token) > 0

    @pytest.mark.asyncio
    async def test_create_category(self, client: AsyncClient, token_factory):
        """创建知识分类"""
        token = await _register_superadmin_via_token_factory(token_factory)

        resp = await client.post(
            "/api/admin/categories",
            headers=_auth_headers(token),
            json={"name": "人事制度", "description": "人事相关制度文档", "scope": "public"},
        )
        assert resp.status_code == 201, f"创建分类失败: {resp.text}"
        data = resp.json()
        assert data["name"] == "人事制度"

    @pytest.mark.asyncio
    async def test_document_upload_and_chunk(self, client: AsyncClient, token_factory):
        """文档创建 → 上传内容 → 分块"""
        token = await _register_superadmin_via_token_factory(token_factory)
        headers = _auth_headers(token)

        resp = await client.post(
            "/api/admin/categories",
            headers=headers,
            json={"name": "考勤制度", "description": "考勤相关文档", "scope": "public"},
        )
        assert resp.status_code == 201
        cat_id = resp.json()["id"]

        resp = await client.post(
            "/api/admin/documents",
            headers=headers,
            json={
                "category_id": cat_id,
                "title": "企业考勤管理制度 v2.0",
                "scope": "public",
                "chunk_strategy": "recursive",
                "chunk_size": 800,
                "chunk_overlap": 200,
            },
        )
        assert resp.status_code == 201, f"创建文档失败: {resp.text}"
        doc = resp.json()
        assert doc["title"] == "企业考勤管理制度 v2.0"
        doc_id = doc["id"]

        resp = await client.post(
            f"/api/admin/documents/{doc_id}/content",
            headers=headers,
            json={"content": DOC_CONTENT, "file_type": "md"},
        )
        assert resp.status_code == 200, f"上传内容失败: {resp.text}"
        assert resp.json()["word_count"] > 0

        resp = await client.post(
            f"/api/admin/documents/{doc_id}/chunk",
            headers=headers,
        )
        assert resp.status_code == 200, f"分块失败: {resp.text}"
        assert resp.json()["chunk_count"] > 0

    @pytest.mark.asyncio
    async def test_review_and_approve(self, client: AsyncClient, token_factory):
        """文档审核通过 → status 变为 online"""
        token = await _register_superadmin_via_token_factory(token_factory)
        headers = _auth_headers(token)

        resp = await client.post(
            "/api/admin/categories",
            headers=headers,
            json={"name": "员工手册", "description": "员工手册", "scope": "public"},
        )
        cat_id = resp.json()["id"]

        resp = await client.post(
            "/api/admin/documents",
            headers=headers,
            json={"category_id": cat_id, "title": "员工考勤手册", "scope": "public"},
        )
        doc_id = resp.json()["id"]

        await client.post(f"/api/admin/documents/{doc_id}/content", headers=headers, json={"content": DOC_CONTENT, "file_type": "md"})
        await client.post(f"/api/admin/documents/{doc_id}/chunk", headers=headers)

        resp = await client.post(
            f"/api/admin/documents/{doc_id}/review",
            headers=headers,
            json={"action": "approve"},
        )
        assert resp.status_code == 200, f"审核失败: {resp.text}"
        doc = resp.json()
        assert doc["review_status"] == "approved"
        assert doc["status"] == "online"

    @pytest.mark.asyncio
    async def test_ai_chat_rag_answer(self, client: AsyncClient, token_factory):
        """完整 RAG 流程: 文档上线 → 同步 → AI 问答"""
        from app.retrieval.fusion import FusionResult

        token = await _register_superadmin_via_token_factory(token_factory)
        headers = _auth_headers(token)

        # 创建分类 + 文档 + 上传 + 分块 + 审核
        resp = await client.post(
            "/api/admin/categories",
            headers=headers,
            json={"name": "综合制度", "description": "制度文件", "scope": "public"},
        )
        cat_id = resp.json()["id"]

        resp = await client.post(
            "/api/admin/documents",
            headers=headers,
            json={"category_id": cat_id, "title": "考勤管理手册", "scope": "public"},
        )
        doc_id = resp.json()["id"]

        await client.post(f"/api/admin/documents/{doc_id}/content", headers=headers, json={"content": DOC_CONTENT, "file_type": "md"})
        await client.post(f"/api/admin/documents/{doc_id}/chunk", headers=headers)
        await client.post(f"/api/admin/documents/{doc_id}/review", headers=headers, json={"action": "approve"})

        # Mock retrieval + LLM
        mock_docs = [
            FusionResult(unique_id="1_0", doc_id=doc_id, chunk_index=0, content="公司实行每周五天工作制，上午 09:00-12:00，下午 13:30-18:00", fused_score=0.95, scope="public", metadata={"title": "考勤管理手册"}),
            FusionResult(unique_id="1_1", doc_id=doc_id, chunk_index=1, content="员工请假需提前一天在 OA 系统提交，年假 5 天，病假不超过 3 天", fused_score=0.9, scope="public", metadata={"title": "考勤管理手册"}),
        ]

        mock_generate_llm = MagicMock()

        async def _gen_stream(messages):
            yield MagicMock(content="根据考勤管理手册，公司实行每周五天工作制，上午9:00至12:00，下午13:30至18:00。员工请假需提前一天在OA系统提交。[来源: 考勤管理手册]")

        mock_generate_llm.astream = _gen_stream

        mock_tools_llm = MagicMock()
        mock_tools_resp = MagicMock()
        mock_tools_resp.tool_calls = []
        mock_tools_resp.content = ""
        mock_tools_llm.bind_tools.return_value.ainvoke = AsyncMock(return_value=mock_tools_resp)

        mock_faq_vector = [0.1] * 1024

        with patch("app.agents.nodes.retrieve.hybrid_retrieve", new=AsyncMock(return_value=mock_docs)):
            with patch("app.agents.nodes.retrieve.rerank", new=AsyncMock(return_value=mock_docs)):
                with patch("app.agents.nodes.faq.FAQ_VECTORS", []):
                    with patch("app.agents.nodes.faq.embed_query", return_value=mock_faq_vector):
                        with patch("app.agents.nodes.generate.create_llm", return_value=mock_generate_llm):
                            with patch("app.agents.nodes.tools.create_llm", return_value=mock_tools_llm):
                                resp = await client.post(
                                    "/api/agent/chat",
                                    json={"message": "公司的工作时间是怎样的？请假需要什么流程？"},
                                )
                                assert resp.status_code == 200, f"AI 问答失败: {resp.text}"
                                data = resp.json()
                                assert "answer" in data
                                assert not data.get("is_blocked", True)
                                assert "考勤" in data["answer"] or "工作" in data["answer"] or "5" in data["answer"]
                                assert data.get("confidence", 0) > 0
