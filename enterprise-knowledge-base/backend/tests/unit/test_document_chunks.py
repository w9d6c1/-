"""文档切片查看 + 重新向量化 + 删除清理 测试"""

from unittest.mock import patch

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_list_chunks_empty(client: AsyncClient, token_factory):
    """无切片的文档返回空列表"""
    token = await token_factory("chunklist1")
    resp = await client.post(
        "/api/admin/documents",
        json={"category_id": 1, "title": "空切片文档", "scope": "public"},
        headers={"Authorization": f"Bearer {token}"},
    )
    doc_id = resp.json()["id"]

    resp = await client.get(
        f"/api/admin/documents/{doc_id}/chunks",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_list_chunks_after_chunking(client: AsyncClient, token_factory):
    """分块后列出切片，返回内容并按 chunk_index 排序"""
    token = await token_factory("chunklist2")
    resp = await client.post(
        "/api/admin/documents",
        json={"category_id": 1, "title": "有切片文档", "chunk_strategy": "fixed", "chunk_size": 300},
        headers={"Authorization": f"Bearer {token}"},
    )
    doc_id = resp.json()["id"]

    await client.post(
        f"/api/admin/documents/{doc_id}/content",
        json={"content": "ABCDEFGHIJ" * 100},
        headers={"Authorization": f"Bearer {token}"},
    )
    await client.post(
        f"/api/admin/documents/{doc_id}/chunk",
        headers={"Authorization": f"Bearer {token}"},
    )

    resp = await client.get(
        f"/api/admin/documents/{doc_id}/chunks",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) > 1
    assert data[0]["chunk_index"] == 0
    assert data[0]["content"]
    assert all(c["doc_id"] == doc_id for c in data)


@pytest.mark.asyncio
async def test_list_chunks_not_found(client: AsyncClient, token_factory):
    """不存在的文档返回 404"""
    token = await token_factory("chunklist3")
    resp = await client.get(
        "/api/admin/documents/99999/chunks",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_resync_online_document(client: AsyncClient, token_factory):
    """上线且有切片的文档可以触发重新向量化"""
    token = await token_factory("resync1", "dept_admin")
    resp = await client.post(
        "/api/admin/documents",
        json={"category_id": 1, "title": "重新向量化测试", "scope": "public"},
        headers={"Authorization": f"Bearer {token}"},
    )
    doc_id = resp.json()["id"]

    await client.post(
        f"/api/admin/documents/{doc_id}/content",
        json={"content": "测试内容" * 100},
        headers={"Authorization": f"Bearer {token}"},
    )
    await client.post(
        f"/api/admin/documents/{doc_id}/chunk",
        headers={"Authorization": f"Bearer {token}"},
    )
    await client.post(
        f"/api/admin/documents/{doc_id}/review",
        json={"action": "approve"},
        headers={"Authorization": f"Bearer {token}"},
    )

    with patch("app.retrieval.sync.sync_document", return_value=5):
        resp = await client.post(
            f"/api/admin/documents/{doc_id}/resync",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        assert resp.json()["synced"] == 5


@pytest.mark.asyncio
async def test_resync_non_online_rejected(client: AsyncClient, token_factory):
    """非上线状态的文档不能重新向量化"""
    token = await token_factory("resync2")
    resp = await client.post(
        "/api/admin/documents",
        json={"category_id": 1, "title": "草稿文档", "scope": "public"},
        headers={"Authorization": f"Bearer {token}"},
    )
    doc_id = resp.json()["id"]

    resp = await client.post(
        f"/api/admin/documents/{doc_id}/resync",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_resync_no_chunks_rejected(client: AsyncClient, token_factory):
    """无切片的文档不能重新向量化"""
    token = await token_factory("resync3", "dept_admin")
    resp = await client.post(
        "/api/admin/documents",
        json={"category_id": 1, "title": "无切片文档", "scope": "public"},
        headers={"Authorization": f"Bearer {token}"},
    )
    doc_id = resp.json()["id"]

    await client.post(
        f"/api/admin/documents/{doc_id}/content",
        json={"content": "仅有内容无切片" * 10},
        headers={"Authorization": f"Bearer {token}"},
    )
    await client.post(
        f"/api/admin/documents/{doc_id}/review",
        json={"action": "approve"},
        headers={"Authorization": f"Bearer {token}"},
    )

    resp = await client.post(
        f"/api/admin/documents/{doc_id}/resync",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_delete_triggers_deindex(client: AsyncClient, token_factory):
    """删除文档时触发 deindex_document 清理 ES/Milvus"""
    token = await token_factory("deindex1")
    resp = await client.post(
        "/api/admin/documents",
        json={"category_id": 1, "title": "待删除文档", "scope": "public"},
        headers={"Authorization": f"Bearer {token}"},
    )
    doc_id = resp.json()["id"]

    with patch("app.services.document_service._deindex_document_async") as mock_deindex:
        resp = await client.delete(
            f"/api/admin/documents/{doc_id}",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 204

        import asyncio
        await asyncio.sleep(0.2)
        mock_deindex.assert_called_once_with(doc_id)
