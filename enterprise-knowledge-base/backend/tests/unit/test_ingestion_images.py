"""采集入库图片关联测试 — 占位符→切片映射与 DocImage 写入"""

import pytest
from unittest.mock import AsyncMock, patch

from sqlalchemy import select

from app.collector.ingestion import ACTION_CREATED, SourceContentService
from app.collector.image_extractor import ExtractedImage
from app.collector.models import RawArticle
from app.models.document import DocChunk, DocImage, KnowledgeDoc

_ARTICLE = RawArticle(
    platform="wechat",
    external_id="wx-img-001",
    title="带图文章",
    html_content="<p>x</p>",
    original_url="https://mp.weixin.qq.com/s/img",
)


@pytest.mark.asyncio
async def test_chunks_strip_placeholders_and_images_associated(db_session):
    svc = SourceContentService(db_session)
    image_text = "第一段内容。\n[[IMG:1]]\n第二段内容。\n[[IMG:2]]\n第三段内容。"
    images = [
        ExtractedImage(seq=1, object_name="article-images/wechat/a/1.jpg", original_url="https://a/1.jpg", content_hash="h1"),
        ExtractedImage(seq=2, object_name="article-images/wechat/a/2.jpg", original_url="https://a/2.jpg", content_hash="h2"),
    ]
    with patch("app.retrieval.sync.sync_document", new=AsyncMock(return_value=2)):
        outcome = await svc.ingest(
            _ARTICLE,
            "第一段内容。\n第二段内容。\n第三段内容。",
            category_id=1,
            image_text=image_text,
            images=images,
        )

    assert outcome.action == ACTION_CREATED
    doc_id = outcome.doc_id

    chunks = (
        await db_session.execute(select(DocChunk).where(DocChunk.doc_id == doc_id).order_by(DocChunk.chunk_index))
    ).scalars().all()
    assert len(chunks) >= 1
    for c in chunks:
        assert "[[IMG:" not in c.content

    rows = (
        await db_session.execute(select(DocImage).where(DocImage.doc_id == doc_id).order_by(DocImage.seq))
    ).scalars().all()
    assert len(rows) == 2
    assert rows[0].seq == 1
    assert rows[1].seq == 2
    assert rows[0].object_name == "article-images/wechat/a/1.jpg"
    assert rows[0].chunk_index is not None


@pytest.mark.asyncio
async def test_raw_html_saved_for_rollback(db_session):
    svc = SourceContentService(db_session)
    with patch("app.retrieval.sync.sync_document", new=AsyncMock(return_value=1)):
        outcome = await svc.ingest(
            _ARTICLE,
            "正文",
            category_id=1,
            raw_html="<p>原文</p><img src='https://a/1.jpg'>",
        )
    doc = await db_session.get(KnowledgeDoc, outcome.doc_id)
    assert doc.raw_text == "<p>原文</p><img src='https://a/1.jpg'>"


@pytest.mark.asyncio
async def test_no_images_writes_no_rows(db_session):
    svc = SourceContentService(db_session)
    with patch("app.retrieval.sync.sync_document", new=AsyncMock(return_value=1)):
        outcome = await svc.ingest(_ARTICLE, "纯文本文章", category_id=1)
    rows = (
        await db_session.execute(select(DocImage).where(DocImage.doc_id == outcome.doc_id))
    ).scalars().all()
    assert rows == []
