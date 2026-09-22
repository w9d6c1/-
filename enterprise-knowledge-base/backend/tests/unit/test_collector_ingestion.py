"""采集入库服务测试（mock sync_document，聚焦去重与来源链接逻辑）"""

import pytest
from unittest.mock import AsyncMock, patch

from sqlalchemy import select

from app.collector.dedup import content_fingerprint, content_hash
from app.collector.ingestion import (
    ACTION_CREATED,
    ACTION_MERGED,
    ACTION_SKIPPED,
    SourceContentService,
)
from app.collector.models import RawArticle
from app.models.collector import DocSourceLink
from app.models.document import DocChunk, KnowledgeDoc

_LONG_TEXT = (
    "特莱顿电渗透脉冲防潮系统通过电场作用阻止水分毛细渗透，适用于地下室与隧道工程。"
    "系统由控制主机、电极网与传感装置组成，可长期稳定运行并实时监测湿度变化。"
)


def _article(platform: str, external_id: str, title: str = "测试文章", text_hint: str = "x") -> RawArticle:
    return RawArticle(
        platform=platform,
        external_id=external_id,
        title=title,
        html_content=f"<p>{text_hint}</p>",
        original_url=f"https://example.com/{platform}/{external_id}",
        source_name=f"{platform}官方号",
    )


@pytest.fixture
def svc(db_session):
    return SourceContentService(db_session)


class TestIngestCreate:
    @pytest.mark.asyncio
    async def test_creates_document_with_source_fields(self, svc, db_session):
        article = _article("wechat", "wx-001", title="公众号文章")
        with patch("app.retrieval.sync.sync_document", new=AsyncMock(return_value=2)):
            outcome = await svc.ingest(article, _LONG_TEXT, category_id=1)

        assert outcome.action == ACTION_CREATED
        assert outcome.doc_id is not None

        doc = await db_session.get(KnowledgeDoc, outcome.doc_id)
        assert doc.scope == "public"
        assert doc.source_type == "wechat"
        assert doc.source_name == "wechat官方号"
        assert doc.original_url == "https://example.com/wechat/wx-001"
        assert doc.status == "online"
        assert doc.review_status == "approved"
        assert doc.content_hash == content_hash(_LONG_TEXT)
        assert doc.content_simhash == content_fingerprint(_LONG_TEXT)
        assert doc.chunk_count >= 1

        chunks = (await db_session.execute(select(DocChunk).where(DocChunk.doc_id == doc.id))).scalars().all()
        assert len(chunks) == doc.chunk_count

        links = (await db_session.execute(select(DocSourceLink).where(DocSourceLink.doc_id == doc.id))).scalars().all()
        assert len(links) == 1
        assert links[0].is_primary is True
        assert links[0].platform == "wechat"
        assert links[0].external_id == "wx-001"


class TestIngestDedup:
    @pytest.mark.asyncio
    async def test_skip_same_external_id(self, svc, db_session):
        article = _article("wechat", "wx-dup")
        with patch("app.retrieval.sync.sync_document", new=AsyncMock(return_value=1)):
            first = await svc.ingest(article, _LONG_TEXT, category_id=1)
            second = await svc.ingest(article, _LONG_TEXT, category_id=1)
        assert first.action == ACTION_CREATED
        assert second.action == ACTION_SKIPPED
        assert second.doc_id == first.doc_id
        assert second.reason == "external_id_exists"

    @pytest.mark.asyncio
    async def test_merge_exact_content_cross_platform(self, svc, db_session):
        wechat = _article("wechat", "wx-100", title="同一篇文章")
        toutiao = _article("toutiao", "tt-100", title="同一篇文章")
        with patch("app.retrieval.sync.sync_document", new=AsyncMock(return_value=1)):
            first = await svc.ingest(wechat, _LONG_TEXT, category_id=1)
            second = await svc.ingest(toutiao, _LONG_TEXT, category_id=1)

        assert first.action == ACTION_CREATED
        assert second.action == ACTION_MERGED
        assert second.doc_id == first.doc_id
        assert second.reason == "exact_content_hash"

        links = (
            (await db_session.execute(select(DocSourceLink).where(DocSourceLink.doc_id == first.doc_id)))
            .scalars().all()
        )
        platforms = {link.platform for link in links}
        assert platforms == {"wechat", "toutiao"}
        primary = [link for link in links if link.is_primary]
        assert len(primary) == 1 and primary[0].platform == "wechat"

    @pytest.mark.asyncio
    async def test_merge_near_duplicate(self, svc, db_session):
        # 预置一篇 content_hash 不匹配但 simhash 相同的文档，强制走近似去重分支
        simhash = content_fingerprint(_LONG_TEXT)
        existing = KnowledgeDoc(
            category_id=1, title="近似文章", scope="public",
            plain_text=_LONG_TEXT, word_count=len(_LONG_TEXT),
            status="online", review_status="approved",
            content_hash="0" * 64, content_simhash=simhash,
        )
        db_session.add(existing)
        await db_session.commit()

        article = _article("zhihu", "zh-200", title="近似文章")
        with patch("app.retrieval.sync.sync_document", new=AsyncMock(return_value=1)):
            outcome = await svc.ingest(article, _LONG_TEXT, category_id=1)

        assert outcome.action == ACTION_MERGED
        assert outcome.doc_id == existing.id
        assert outcome.reason == "near_duplicate"

    @pytest.mark.asyncio
    async def test_skip_empty_content(self, svc, db_session):
        article = _article("wechat", "wx-empty")
        outcome = await svc.ingest(article, "   ", category_id=1)
        assert outcome.action == ACTION_SKIPPED
        assert outcome.reason == "empty_content"
