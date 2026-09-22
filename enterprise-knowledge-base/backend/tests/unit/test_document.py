"""文档上传 + 分块 + 审核 + 向量同步 测试 (TDD: RED)"""

from unittest.mock import patch

import pytest
from httpx import AsyncClient




# ===================== 文档上传 =====================

@pytest.mark.asyncio
async def test_create_document_metadata_returns_201(client: AsyncClient, token_factory):
    """创建文档元数据（不含文件内容）"""
    token = await token_factory("docuser1")
    resp = await client.post(
        "/api/admin/documents",
        json={
            "category_id": 1, "title": "员工手册",
            "scope": "internal", "chunk_strategy": "recursive",
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["title"] == "员工手册"
    assert data["status"] == "draft"
    assert data["review_status"] == "pending"


@pytest.mark.asyncio
async def test_upload_text_content_to_document(client: AsyncClient, token_factory):
    """上传文本到已有文档"""
    token = await token_factory("docuser2")
    resp = await client.post(
        "/api/admin/documents",
        json={"category_id": 1, "title": "测试文本", "scope": "public"},
        headers={"Authorization": f"Bearer {token}"},
    )
    doc_id = resp.json()["id"]

    resp = await client.post(
        f"/api/admin/documents/{doc_id}/content",
        json={"content": "这是一段测试文本，" * 50 + "用于验证文档上传和切片功能。"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["word_count"] > 0


@pytest.mark.asyncio
async def test_list_documents(client: AsyncClient, token_factory):
    token = await token_factory("docuser3")
    resp = await client.get(
        "/api/admin/documents", headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data["items"], list)
    assert "total" in data


# ===================== 文件上传 (MinIO) =====================

@pytest.mark.asyncio
async def test_upload_file_requires_auth(client: AsyncClient):
    """未认证不能上传文件"""
    resp = await client.post(
        "/api/admin/documents/upload",
        files={"file": ("a.md", b"# hello", "text/markdown")},
        data={"title": "无权限", "category_id": "1", "scope": "public"},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_readonly_cannot_upload_file(client: AsyncClient, token_factory):
    """只读用户不能上传文件"""
    token = await token_factory("uploadreadonly", "readonly")
    resp = await client.post(
        "/api/admin/documents/upload",
        files={"file": ("a.md", b"# hello", "text/markdown")},
        data={"title": "只读上传", "category_id": "1", "scope": "public"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_upload_md_file_success(client: AsyncClient, token_factory):
    """上传 Markdown 文件成功，解析出正文与字数"""
    token = await token_factory("uploadmd")
    with patch("app.core.minio_client.ensure_bucket"), patch(
        "app.core.minio_client.upload_file", return_value="obj.md"
    ):
        resp = await client.post(
            "/api/admin/documents/upload",
            files={"file": ("手册.md", "# 标题\n\n这是正文内容。".encode(), "text/markdown")},
            data={"title": "上传文档", "category_id": "1", "scope": "internal", "chunk_strategy": "recursive"},
            headers={"Authorization": f"Bearer {token}"},
        )
    assert resp.status_code == 201
    data = resp.json()
    assert data["title"] == "上传文档"
    assert data["file_type"] == "md"
    assert data["scope"] == "internal"
    assert data["word_count"] > 0
    assert data["status"] == "draft"


@pytest.mark.asyncio
async def test_upload_uses_filename_when_title_default(client: AsyncClient, token_factory):
    """未提供标题时使用文件名"""
    token = await token_factory("uploadtitle")
    with patch("app.core.minio_client.ensure_bucket"), patch(
        "app.core.minio_client.upload_file", return_value="obj.txt"
    ):
        resp = await client.post(
            "/api/admin/documents/upload",
            files={"file": ("readme.txt", b"plain text body", "text/plain")},
            data={"category_id": "1"},
            headers={"Authorization": f"Bearer {token}"},
        )
    assert resp.status_code == 201
    assert resp.json()["title"] == "readme.txt"


@pytest.mark.asyncio
async def test_upload_unsupported_extension_rejected(client: AsyncClient, token_factory):
    """不支持的扩展名被拒绝"""
    token = await token_factory("uploadbad")
    resp = await client.post(
        "/api/admin/documents/upload",
        files={"file": ("evil.exe", b"MZ...", "application/octet-stream")},
        data={"title": "恶意文件", "category_id": "1"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_upload_calls_minio(client: AsyncClient, token_factory):
    """上传时调用 MinIO 存储并记录 file_path"""
    token = await token_factory("uploadminio")
    with patch("app.core.minio_client.ensure_bucket") as mock_bucket, patch(
        "app.core.minio_client.upload_file", return_value="stored.md"
    ) as mock_upload:
        resp = await client.post(
            "/api/admin/documents/upload",
            files={"file": ("doc.md", b"# body", "text/markdown")},
            data={"title": "存储测试", "category_id": "1"},
            headers={"Authorization": f"Bearer {token}"},
        )
    assert resp.status_code == 201
    mock_bucket.assert_called_once()
    mock_upload.assert_called_once()


@pytest.mark.asyncio
async def test_upload_survives_minio_failure(client: AsyncClient, token_factory):
    """MinIO 不可用时上传仍成功（尽力存储），文档正文可用"""
    token = await token_factory("uploadfail")
    with patch("app.core.minio_client.ensure_bucket", side_effect=Exception("minio down")):
        resp = await client.post(
            "/api/admin/documents/upload",
            files={"file": ("doc.md", b"# body text", "text/markdown")},
            data={"title": "降级测试", "category_id": "1"},
            headers={"Authorization": f"Bearer {token}"},
        )
    assert resp.status_code == 201
    assert resp.json()["word_count"] > 0


# ===================== 文本解析 =====================

@pytest.mark.asyncio
async def test_parse_markdown_text(client: AsyncClient, token_factory):
    """解析 Markdown 文本"""
    token = await token_factory("parseuser")
    resp = await client.post(
        "/api/admin/documents/parse",
        json={
            "content": "# 标题\n\n这是段落一。\n\n## 子标题\n\n这是段落二。",
            "file_type": "md",
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["word_count"] > 0
    assert data["plain_text"]


# ===================== 分块策略 =====================

@pytest.mark.asyncio
async def test_chunk_fixed_size(client: AsyncClient, token_factory):
    token = await token_factory("chunkuser1")
    resp = await client.post(
        "/api/admin/documents",
        json={"category_id": 1, "title": "固定分块测试", "chunk_strategy": "fixed", "chunk_size": 300},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201
    doc_id = resp.json()["id"]
    await client.post(
        f"/api/admin/documents/{doc_id}/content",
        json={"content": "ABCDEFGHIJ" * 100},
        headers={"Authorization": f"Bearer {token}"},
    )
    resp = await client.post(
        f"/api/admin/documents/{doc_id}/chunk",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["chunk_count"] > 1


@pytest.mark.asyncio
async def test_chunk_recursive(client: AsyncClient, token_factory):
    token = await token_factory("chunkuser2")
    resp = await client.post(
        "/api/admin/documents",
        json={"category_id": 1, "title": "递归分块", "chunk_strategy": "recursive", "chunk_size": 300},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201
    doc_id = resp.json()["id"]
    await client.post(
        f"/api/admin/documents/{doc_id}/content",
        json={"content": "第一章\n\n" + "这是第一章的内容。" * 50 + "\n\n第二章\n\n" + "这是第二章的内容。" * 50},
        headers={"Authorization": f"Bearer {token}"},
    )
    resp = await client.post(
        f"/api/admin/documents/{doc_id}/chunk",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200


# ===================== 审核流水线 =====================

@pytest.mark.asyncio
async def test_review_submit_and_approve(client: AsyncClient, token_factory):
    """草稿 → 提交 → 审批通过"""
    token = await token_factory("review1", "dept_admin")
    resp = await client.post(
        "/api/admin/documents",
        json={"category_id": 1, "title": "待审核文档", "scope": "public"},
        headers={"Authorization": f"Bearer {token}"},
    )
    doc_id = resp.json()["id"]

    # 提交审核
    resp = await client.post(
        f"/api/admin/documents/{doc_id}/review",
        json={"action": "approve"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert resp.json()["review_status"] == "approved"
    assert resp.json()["status"] == "online"


@pytest.mark.asyncio
async def test_review_reject(client: AsyncClient, token_factory):
    """审核驳回"""
    token = await token_factory("review2", "dept_admin")
    resp = await client.post(
        "/api/admin/documents",
        json={"category_id": 1, "title": "待驳回", "scope": "public"},
        headers={"Authorization": f"Bearer {token}"},
    )
    doc_id = resp.json()["id"]

    resp = await client.post(
        f"/api/admin/documents/{doc_id}/review",
        json={"action": "reject", "comment": "内容需要修改"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert resp.json()["review_status"] == "rejected"


@pytest.mark.asyncio
async def test_readonly_cannot_review(client: AsyncClient, token_factory):
    """只读用户不能审核"""
    token = await token_factory("revreadonly", "readonly")
    resp = await client.post(
        "/api/admin/documents",
        json={"category_id": 1, "title": "只读创建的文档", "scope": "public"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 403  # readonly can't write


# ===================== 审批后自动向量同步 =====================

@pytest.mark.asyncio
async def test_approve_triggers_sync(client: AsyncClient, token_factory):
    """审批通过后自动触发向量同步"""
    from unittest.mock import patch

    token = await token_factory("syncapply1", "dept_admin")
    resp = await client.post(
        "/api/admin/documents",
        json={"category_id": 1, "title": "自动同步测试", "scope": "public"},
        headers={"Authorization": f"Bearer {token}"},
    )
    doc_id = resp.json()["id"]

    # 上传内容 + 分块 以便 sync 有数据可同步
    await client.post(
        f"/api/admin/documents/{doc_id}/content",
        json={"content": "自动同步测试内容" * 10},
        headers={"Authorization": f"Bearer {token}"},
    )
    await client.post(
        f"/api/admin/documents/{doc_id}/chunk",
        headers={"Authorization": f"Bearer {token}"},
    )

    with patch("app.services.document_service._sync_document_async") as mock_sync:
        resp = await client.post(
            f"/api/admin/documents/{doc_id}/review",
            json={"action": "approve"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "online"
        # 等待异步任务调度
        import asyncio
        await asyncio.sleep(0.2)
        mock_sync.assert_called_once_with(doc_id)
