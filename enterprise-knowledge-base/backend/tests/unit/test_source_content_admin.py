"""多源内容管理 API 测试"""

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from unittest.mock import AsyncMock, patch

from app.models.collector import CollectorSyncLog, CollectorSyncState, DocSourceLink
from app.models.document import KnowledgeDoc


async def _seed_doc(db, doc_id=300, source_type="wechat", title="公众号文章", status="online"):
    doc = KnowledgeDoc(
        id=doc_id, category_id=1, title=title, scope="public",
        source_type=source_type, source_name="官方公众号",
        original_url="https://mp.weixin.qq.com/s/x",
        plain_text="内容", word_count=2, chunk_count=1,
        status=status, review_status="approved",
    )
    db.add(doc)
    await db.flush()
    db.add(DocSourceLink(
        doc_id=doc_id, platform=source_type, external_id=f"ext-{doc_id}",
        original_url="https://mp.weixin.qq.com/s/x", source_name="官方公众号", is_primary=True,
    ))
    await db.commit()
    return doc


@pytest.mark.asyncio
async def test_list_and_filter_source_contents(client: AsyncClient, token_factory, db_session):
    token = await token_factory("sc_user1")
    await _seed_doc(db_session, doc_id=300, source_type="wechat", title="微信文章A")
    await _seed_doc(db_session, doc_id=301, source_type="toutiao", title="头条文章B")

    resp = await client.get("/api/admin/source-contents", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    assert resp.json()["total"] >= 2

    resp2 = await client.get(
        "/api/admin/source-contents?source_type=wechat", headers={"Authorization": f"Bearer {token}"}
    )
    items = resp2.json()["items"]
    assert items and all(i["source_type"] == "wechat" for i in items)


@pytest.mark.asyncio
async def test_list_excludes_internal(client: AsyncClient, token_factory, db_session):
    token = await token_factory("sc_user2")
    db_session.add(KnowledgeDoc(
        id=310, category_id=1, title="内部文档", scope="internal",
        source_type="internal", status="online", review_status="approved",
    ))
    await db_session.commit()
    await _seed_doc(db_session, doc_id=311, source_type="wechat", title="外部文章")

    resp = await client.get("/api/admin/source-contents", headers={"Authorization": f"Bearer {token}"})
    ids = [i["id"] for i in resp.json()["items"]]
    assert 310 not in ids
    assert 311 in ids


@pytest.mark.asyncio
async def test_detail_with_source_links(client: AsyncClient, token_factory, db_session):
    token = await token_factory("sc_user3")
    await _seed_doc(db_session, doc_id=320)
    resp = await client.get("/api/admin/source-contents/320", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == 320
    assert len(data["source_links"]) == 1
    assert data["source_links"][0]["is_primary"] is True


@pytest.mark.asyncio
async def test_detail_not_found(client: AsyncClient, token_factory):
    token = await token_factory("sc_user4")
    resp = await client.get("/api/admin/source-contents/999999", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_status_change_offline(client: AsyncClient, token_factory, db_session):
    token = await token_factory("sc_user5")
    await _seed_doc(db_session, doc_id=330, status="online")
    with patch("app.retrieval.sync.deindex_document", new=AsyncMock(return_value=1)), \
         patch("app.retrieval.sync.sync_document", new=AsyncMock(return_value=1)):
        resp = await client.put(
            "/api/admin/source-contents/330/status",
            json={"status": "offline"},
            headers={"Authorization": f"Bearer {token}"},
        )
    assert resp.status_code == 200
    assert resp.json()["status"] == "offline"


@pytest.mark.asyncio
async def test_delete_requires_delete_permission(client: AsyncClient, token_factory, db_session):
    await _seed_doc(db_session, doc_id=340)
    # operator 无 delete 权限
    op_token = await token_factory("sc_user6a", role="operator")
    resp = await client.delete("/api/admin/source-contents/340", headers={"Authorization": f"Bearer {op_token}"})
    assert resp.status_code == 403

    admin_token = await token_factory("sc_user6b", role="dept_admin")
    with patch("app.retrieval.sync.deindex_document", new=AsyncMock(return_value=1)):
        resp2 = await client.delete("/api/admin/source-contents/340", headers={"Authorization": f"Bearer {admin_token}"})
    assert resp2.status_code == 200
    assert resp2.json()["success"] is True
    assert await db_session.get(KnowledgeDoc, 340) is None


@pytest.mark.asyncio
async def test_readonly_cannot_change_status(client: AsyncClient, token_factory, db_session):
    token = await token_factory("sc_user7", role="readonly")
    await _seed_doc(db_session, doc_id=350)
    resp = await client.put(
        "/api/admin/source-contents/350/status",
        json={"status": "offline"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_sync_states_and_logs(client: AsyncClient, token_factory, db_session):
    token = await token_factory("sc_user8")
    db_session.add(CollectorSyncState(platform="wechat", last_status="success", last_cursor="20"))
    db_session.add(CollectorSyncLog(platform="wechat", status="success", fetched_count=5, ingested_count=3, duplicated_count=2))
    await db_session.commit()

    resp = await client.get("/api/admin/source-contents/sync-states", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    assert any(s["platform"] == "wechat" and s["last_status"] == "success" for s in resp.json())

    resp2 = await client.get("/api/admin/source-contents/sync-logs", headers={"Authorization": f"Bearer {token}"})
    assert resp2.status_code == 200
    assert resp2.json()["total"] >= 1


@pytest.mark.asyncio
async def test_trigger_sync(client: AsyncClient, token_factory, db_session):
    token = await token_factory("sc_user9")
    from app.collector.models import PlatformSyncResult, SyncSummary

    summary = SyncSummary(results=[PlatformSyncResult(platform="wechat", fetched=2, ingested=2)])
    with patch("app.services.source_content_admin.CollectorPipeline") as mock_pipeline:
        mock_pipeline.return_value.sync_all = AsyncMock(return_value=summary)
        resp = await client.post(
            "/api/admin/source-contents/sync",
            json={"platforms": ["wechat"]},
            headers={"Authorization": f"Bearer {token}"},
        )
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_ingested"] == 2
    assert data["all_ok"] is True


@pytest.mark.asyncio
async def test_merge_documents(client: AsyncClient, token_factory, db_session):
    token = await token_factory("sc_user10")
    await _seed_doc(db_session, doc_id=360, title="主文档", source_type="wechat")
    await _seed_doc(db_session, doc_id=361, title="重复文档", source_type="toutiao")

    with patch("app.retrieval.sync.deindex_document", new=AsyncMock(return_value=1)):
        resp = await client.post(
            "/api/admin/source-contents/merge",
            json={"primary_doc_id": 360, "duplicate_doc_id": 361},
            headers={"Authorization": f"Bearer {token}"},
        )
    assert resp.status_code == 200
    assert resp.json()["id"] == 360
    assert await db_session.get(KnowledgeDoc, 361) is None

    links = (await db_session.execute(select(DocSourceLink).where(DocSourceLink.doc_id == 360))).scalars().all()
    assert "toutiao" in {link.platform for link in links}


async def _seed_draft_doc(db, doc_id):
    """草稿来源文档：无永久 original_url，external_id 为 draft:{media_id}:{idx}"""
    doc = KnowledgeDoc(
        id=doc_id, category_id=1, title="草稿文章", scope="public",
        source_type="wechat", source_name="官方公众号",
        original_url=None, plain_text="内容", word_count=2, chunk_count=1,
        status="online", review_status="approved",
    )
    db.add(doc)
    await db.flush()
    db.add(DocSourceLink(
        doc_id=doc_id, platform="wechat", external_id=f"draft:media{doc_id}:0",
        original_url=None, source_name="官方公众号", is_primary=True,
    ))
    await db.commit()
    return doc


@pytest.mark.asyncio
async def test_preview_url_returns_original_url(client: AsyncClient, token_factory, db_session):
    """有永久链接的文档直接返回原始链接"""
    token = await token_factory("pv_user1")
    await _seed_doc(db_session, doc_id=370)
    resp = await client.get(
        "/api/admin/source-contents/370/preview-url",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert resp.json()["url"] == "https://mp.weixin.qq.com/s/x"


@pytest.mark.asyncio
async def test_preview_url_resolves_draft_via_api(client: AsyncClient, token_factory, db_session):
    """草稿来源文档实时调微信 draft/get 解析预览链接"""
    token = await token_factory("pv_user2")
    await _seed_draft_doc(db_session, doc_id=371)

    fake_collector = AsyncMock()
    fake_collector.resolve_draft_url = AsyncMock(
        return_value="https://mp.weixin.qq.com/s?tempkey=abc"
    )
    with patch("app.api.admin.source_content.get_collector", return_value=fake_collector):
        resp = await client.get(
            "/api/admin/source-contents/371/preview-url",
            headers={"Authorization": f"Bearer {token}"},
        )
    assert resp.status_code == 200
    assert resp.json()["url"] == "https://mp.weixin.qq.com/s?tempkey=abc"
    fake_collector.resolve_draft_url.assert_awaited_once_with("media371", 0)


@pytest.mark.asyncio
async def test_preview_url_draft_unresolvable_404(client: AsyncClient, token_factory, db_session):
    """草稿解析失败（已删除等）返回 404"""
    token = await token_factory("pv_user3")
    await _seed_draft_doc(db_session, doc_id=372)

    fake_collector = AsyncMock()
    fake_collector.resolve_draft_url = AsyncMock(return_value=None)
    with patch("app.api.admin.source_content.get_collector", return_value=fake_collector):
        resp = await client.get(
            "/api/admin/source-contents/372/preview-url",
            headers={"Authorization": f"Bearer {token}"},
        )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_preview_url_not_found(client: AsyncClient, token_factory):
    token = await token_factory("pv_user4")
    resp = await client.get(
        "/api/admin/source-contents/999999/preview-url",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 404
