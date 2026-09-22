"""文档清洗集成测试 — 上传自动清洗 + 存量重清洗 API (TDD: RED)"""

from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient

from app.services.text_cleaner import clean_document_text

DIRTY_MD = (
    "=== Page 1 ===\n"
    "安全验收说明\n"
    "表格\n"
    "检查项\n"
    "物理隔\n"
    "离\n"
    "=== Page 2 ===\n"
    "结束 段落\n"
)


async def _create_doc_with_content(client: AsyncClient, token: str, title: str, content: str) -> int:
    resp = await client.post(
        "/api/admin/documents",
        json={"category_id": 1, "title": title, "scope": "public"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201
    doc_id = resp.json()["id"]
    resp = await client.post(
        f"/api/admin/documents/{doc_id}/content",
        json={"content": content, "file_type": "md"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    return doc_id


@pytest.mark.asyncio
async def test_upload_md_file_auto_cleans(client: AsyncClient, token_factory):
    """上传含垃圾标记的 md 文件后自动清洗"""
    token = await token_factory("cleanupload1")
    with patch("app.core.minio_client.ensure_bucket"), patch(
        "app.core.minio_client.upload_file", return_value="obj.md"
    ):
        resp = await client.post(
            "/api/admin/documents/upload",
            files={"file": ("脏文档.md", DIRTY_MD.encode(), "text/markdown")},
            data={"title": "自动清洗", "category_id": "1", "scope": "public"},
            headers={"Authorization": f"Bearer {token}"},
        )
    assert resp.status_code == 201
    data = resp.json()
    assert data["clean_status"] == "cleaned"

    detail = await client.get(
        f"/api/admin/documents/{data['id']}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert detail.status_code == 200
    body = detail.json()
    assert "=== Page" not in body["plain_text"]
    assert "表格" not in body["plain_text"].split("\n")
    assert "物理隔离" in body["plain_text"]
    assert "=== Page 1 ===" in body["raw_text"]


@pytest.mark.asyncio
async def test_upload_with_auto_clean_disabled(client: AsyncClient, token_factory):
    """auto_clean=false 时跳过清洗"""
    token = await token_factory("cleanupload2")
    with patch("app.core.minio_client.ensure_bucket"), patch(
        "app.core.minio_client.upload_file", return_value="obj.md"
    ):
        resp = await client.post(
            "/api/admin/documents/upload",
            files={"file": ("原文.md", DIRTY_MD.encode(), "text/markdown")},
            data={
                "title": "跳过清洗", "category_id": "1", "scope": "public",
                "auto_clean": "false",
            },
            headers={"Authorization": f"Bearer {token}"},
        )
    assert resp.status_code == 201
    data = resp.json()
    assert data["clean_status"] == "skipped"

    detail = await client.get(
        f"/api/admin/documents/{data['id']}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert "=== Page 1 ===" in detail.json()["plain_text"]


@pytest.mark.asyncio
async def test_content_endpoint_auto_cleans(client: AsyncClient, token_factory):
    """粘贴内容入口同样自动清洗"""
    token = await token_factory("cleancontent")
    doc_id = await _create_doc_with_content(client, token, "粘贴清洗", DIRTY_MD)
    detail = await client.get(
        f"/api/admin/documents/{doc_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    body = detail.json()
    assert body["clean_status"] == "cleaned"
    assert "=== Page" not in body["plain_text"]


@pytest.mark.asyncio
async def test_clean_endpoint_cleans_existing_document(client: AsyncClient, token_factory):
    """重清洗接口：对已有脏文档执行清洗并返回报告"""
    token = await token_factory("cleandoc1")
    with patch("app.core.minio_client.ensure_bucket"), patch(
        "app.core.minio_client.upload_file", return_value="obj.md"
    ):
        resp = await client.post(
            "/api/admin/documents/upload",
            files={"file": ("存量.md", DIRTY_MD.encode(), "text/markdown")},
            data={
                "title": "存量文档", "category_id": "1", "scope": "public",
                "auto_clean": "false",
            },
            headers={"Authorization": f"Bearer {token}"},
        )
    doc_id = resp.json()["id"]

    resp = await client.post(
        f"/api/admin/documents/{doc_id}/clean",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["clean_status"] == "cleaned"
    assert data["report"]["removed_page_markers"] == 2
    assert data["report"]["removed_placeholders"] == 1

    detail = await client.get(
        f"/api/admin/documents/{doc_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert "=== Page" not in detail.json()["plain_text"]


@pytest.mark.asyncio
async def test_clean_endpoint_default_no_llm(client: AsyncClient, token_factory):
    """默认不走 LLM，llm_enhanced 为 False"""
    token = await token_factory("cleannollm")
    doc_id = await _create_doc_with_content(client, token, "默认清洗", DIRTY_MD)
    resp = await client.post(
        f"/api/admin/documents/{doc_id}/clean",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert resp.json()["report"]["llm_enhanced"] is False


@pytest.mark.asyncio
async def test_clean_endpoint_use_llm_flag(client: AsyncClient, token_factory):
    """use_llm=true 时调用 LLM 增强层"""
    token = await token_factory("cleanllmflag")
    doc_id = await _create_doc_with_content(client, token, "LLM清洗", DIRTY_MD)
    fake = clean_document_text("安全验收\n物理隔离")
    with patch(
        "app.services.document_service.llm_enhance_clean",
        new=AsyncMock(return_value=fake),
    ) as mock_enhance:
        resp = await client.post(
            f"/api/admin/documents/{doc_id}/clean",
            json={"use_llm": True},
            headers={"Authorization": f"Bearer {token}"},
        )
    assert resp.status_code == 200
    mock_enhance.assert_awaited_once()
    _, kwargs = mock_enhance.call_args
    assert kwargs.get("use_llm") is True


@pytest.mark.asyncio
async def test_clean_endpoint_requires_auth(client: AsyncClient):
    resp = await client.post("/api/admin/documents/1/clean")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_clean_endpoint_not_found(client: AsyncClient, token_factory):
    token = await token_factory("cleannf")
    resp = await client.post(
        "/api/admin/documents/99999/clean",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_clean_endpoint_empty_document(client: AsyncClient, token_factory):
    """无内容文档清洗返回 400"""
    token = await token_factory("cleanempty")
    resp = await client.post(
        "/api/admin/documents",
        json={"category_id": 1, "title": "空文档", "scope": "public"},
        headers={"Authorization": f"Bearer {token}"},
    )
    doc_id = resp.json()["id"]
    resp = await client.post(
        f"/api/admin/documents/{doc_id}/clean",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_clean_is_idempotent(client: AsyncClient, token_factory):
    token = await token_factory("cleanidem")
    doc_id = await _create_doc_with_content(client, token, "幂等", DIRTY_MD)
    first = await client.post(
        f"/api/admin/documents/{doc_id}/clean",
        headers={"Authorization": f"Bearer {token}"},
    )
    second = await client.post(
        f"/api/admin/documents/{doc_id}/clean",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert first.status_code == 200
    assert second.status_code == 200
    d1 = await client.get(f"/api/admin/documents/{doc_id}", headers={"Authorization": f"Bearer {token}"})
    text_after = d1.json()["plain_text"]
    assert "=== Page" not in text_after


@pytest.mark.asyncio
async def test_bulk_clean(client: AsyncClient, token_factory):
    token = await token_factory("cleanbulk")
    id1 = await _create_doc_with_content(client, token, "批量1", DIRTY_MD)
    id2 = await _create_doc_with_content(client, token, "批量2", DIRTY_MD)

    resp = await client.post(
        "/api/admin/documents/bulk-clean",
        json={"ids": [id1, id2]},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["cleaned"] == 2
    assert data["failed"] == []

    for doc_id in (id1, id2):
        detail = await client.get(
            f"/api/admin/documents/{doc_id}",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert detail.json()["clean_status"] == "cleaned"


@pytest.mark.asyncio
async def test_bulk_clean_empty_ids_rejected(client: AsyncClient, token_factory):
    token = await token_factory("cleanbulkempty")
    resp = await client.post(
        "/api/admin/documents/bulk-clean",
        json={"ids": []},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_readonly_cannot_clean(client: AsyncClient, token_factory):
    token = await token_factory("cleanro", "readonly")
    resp = await client.post(
        "/api/admin/documents/1/clean",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_clean_pdf_document_preserves_line_structure(db_session):
    """PDF/DOCX 文档重清洗保持行结构（与上传流程一致，不被 parse_text 压缩空白）"""
    from app.models.document import KnowledgeDoc
    from app.schemas.user import UserCreate
    from app.services.document_service import DocumentService
    from app.services.user_service import UserService

    user = await UserService(db_session).create(UserCreate(
        username="cleanpdf", password="SecureP@ss1",
        password_confirm="SecureP@ss1", role="superadmin",
    ))
    structured = "=== Page 1 ===\n# 标题\n内容A\n内容B"
    doc = KnowledgeDoc(
        category_id=1, title="PDF结构", scope="public", file_type="pdf",
        plain_text=structured, raw_text=structured, word_count=len(structured),
    )
    db_session.add(doc)
    await db_session.commit()
    await db_session.refresh(doc)

    result = await DocumentService(db_session).clean(doc.id, user)
    assert result is not None
    cleaned_doc, _ = result
    assert "=== Page" not in cleaned_doc.plain_text
    assert "# 标题" in cleaned_doc.plain_text
    assert "\n" in cleaned_doc.plain_text.strip()
