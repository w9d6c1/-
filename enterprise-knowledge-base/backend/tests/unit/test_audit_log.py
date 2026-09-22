"""操作日志 测试 — 查询 + 过滤 + 导出 + CRUD 验证"""

import asyncio
from unittest.mock import patch

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_list_operations_empty(client: AsyncClient, token_factory):
    token = await token_factory("audit1")
    resp = await client.get(
        "/api/admin/operations", headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "items" in data
    assert "total" in data


@pytest.mark.asyncio
async def test_document_create_calls_log(client: AsyncClient, token_factory):
    token = await token_factory("auditdoc")
    with patch("app.api.admin.document.log_operation_async") as mock_log:
        resp = await client.post(
            "/api/admin/documents",
            json={"category_id": 1, "title": "审计测试文档", "scope": "public"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 201
        await asyncio.sleep(0.2)
        mock_log.assert_called()
        kwargs = mock_log.call_args.kwargs
        assert kwargs["operation_type"] == "create"
        assert kwargs["target_table"] == "knowledge_doc"


@pytest.mark.asyncio
async def test_document_delete_calls_log(client: AsyncClient, token_factory):
    token = await token_factory("auditdel")
    resp = await client.post(
        "/api/admin/documents",
        json={"category_id": 1, "title": "待删审计文档", "scope": "public"},
        headers={"Authorization": f"Bearer {token}"},
    )
    doc_id = resp.json()["id"]

    with patch("app.api.admin.document.log_operation_async") as mock_log:
        resp = await client.delete(
            f"/api/admin/documents/{doc_id}",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 204
        await asyncio.sleep(0.2)
        mock_log.assert_called()
        kwargs = mock_log.call_args.kwargs
        assert kwargs["operation_type"] == "delete"
        assert kwargs["target_table"] == "knowledge_doc"


@pytest.mark.asyncio
async def test_synonym_create_calls_log(client: AsyncClient, token_factory):
    token = await token_factory("auditsyn")
    with patch("app.api.admin.dictionary.log_operation_async") as mock_log:
        resp = await client.post(
            "/api/admin/synonyms",
            json={"word": "审计词", "synonyms": ["测试"], "scope": "public"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 201
        await asyncio.sleep(0.2)
        mock_log.assert_called()
        kwargs = mock_log.call_args.kwargs
        assert kwargs["operation_type"] == "create"
        assert kwargs["target_table"] == "synonym"


@pytest.mark.asyncio
async def test_filter_by_operation_type(client: AsyncClient, token_factory):
    token = await token_factory("auditfilt")
    resp = await client.get(
        "/api/admin/operations?operation_type=query",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    for item in data["items"]:
        assert item["operation_type"] == "query"


@pytest.mark.asyncio
async def test_export_csv(client: AsyncClient, token_factory):
    token = await token_factory("auditexport")
    resp = await client.get(
        "/api/admin/operations/export",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert "text/csv" in resp.headers.get("content-type", "")


@pytest.mark.asyncio
async def test_filter_by_date_range(client: AsyncClient, token_factory):
    token = await token_factory("auditdate")
    resp = await client.get(
        "/api/admin/operations?start_date=2000-01-01&end_date=2099-12-31",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_unauthorized_cannot_access(client: AsyncClient):
    resp = await client.get("/api/admin/operations")
    assert resp.status_code == 401
