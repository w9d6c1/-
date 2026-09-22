"""多源内容管理业务逻辑 — 列表/详情/上下架/删除/同步触发/去重合并/状态日志。"""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.collector.models import SyncSummary
from app.collector.pipeline import CollectorPipeline
from app.core.config import settings
from app.core.logging import logger
from app.models.collector import CollectorSyncLog, CollectorSyncState, DocSourceLink
from app.models.document import DocChunk, KnowledgeDoc


class SourceContentAdminService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def list(
        self,
        *,
        page: int = 1,
        page_size: int = 20,
        source_type: str | None = None,
        status: str | None = None,
        search: str | None = None,
    ) -> tuple[list[KnowledgeDoc], int]:
        stmt = select(KnowledgeDoc).where(
            KnowledgeDoc.scope == "public",
            KnowledgeDoc.source_type != "internal",
        )
        if source_type:
            stmt = stmt.where(KnowledgeDoc.source_type == source_type)
        if status:
            stmt = stmt.where(KnowledgeDoc.status == status)
        if search:
            stmt = stmt.where(KnowledgeDoc.title.like(f"%{search}%"))

        count_stmt = select(func.count()).select_from(stmt.subquery())
        total = (await self.db.execute(count_stmt)).scalar() or 0

        stmt = stmt.order_by(KnowledgeDoc.id.desc()).offset((page - 1) * page_size).limit(page_size)
        items = list((await self.db.execute(stmt)).scalars())
        return items, total

    async def get(self, doc_id: int) -> KnowledgeDoc | None:
        return await self.db.get(KnowledgeDoc, doc_id)

    async def get_source_links(self, doc_id: int) -> list[DocSourceLink]:
        stmt = select(DocSourceLink).where(DocSourceLink.doc_id == doc_id).order_by(DocSourceLink.is_primary.desc())
        return list((await self.db.execute(stmt)).scalars())

    async def set_status(self, doc_id: int, status: str) -> KnowledgeDoc | None:
        doc = await self.db.get(KnowledgeDoc, doc_id)
        if doc is None:
            return None
        doc.status = status
        await self.db.commit()
        await self.db.refresh(doc)

        from app.retrieval.sync import deindex_document, sync_document

        if status == "online":
            await sync_document(self.db, doc_id)
        else:
            await deindex_document(doc_id)
        logger.info("source_content_status_changed", doc_id=doc_id, status=status)
        return doc

    async def delete(self, doc_id: int) -> bool:
        doc = await self.db.get(KnowledgeDoc, doc_id)
        if doc is None:
            return False

        from app.retrieval.sync import deindex_document

        chunks = (await self.db.execute(select(DocChunk).where(DocChunk.doc_id == doc_id))).scalars()
        for chunk in chunks:
            await self.db.delete(chunk)
        links = (await self.db.execute(select(DocSourceLink).where(DocSourceLink.doc_id == doc_id))).scalars()
        for link in links:
            await self.db.delete(link)
        await self.db.delete(doc)
        await self.db.commit()
        await deindex_document(doc_id)
        return True

    async def get_sync_states(self) -> list[CollectorSyncState]:
        stmt = select(CollectorSyncState).order_by(CollectorSyncState.platform)
        return list((await self.db.execute(stmt)).scalars())

    async def get_sync_logs(
        self,
        *,
        platform: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[CollectorSyncLog], int]:
        stmt = select(CollectorSyncLog)
        if platform:
            stmt = stmt.where(CollectorSyncLog.platform == platform)
        count_stmt = select(func.count()).select_from(stmt.subquery())
        total = (await self.db.execute(count_stmt)).scalar() or 0
        stmt = stmt.order_by(CollectorSyncLog.started_at.desc()).offset((page - 1) * page_size).limit(page_size)
        items = list((await self.db.execute(stmt)).scalars())
        return items, total

    async def trigger_sync(self, platforms: list[str] | None = None) -> SyncSummary:
        pipeline = CollectorPipeline(self.db, category_id=settings.collector_default_category_id)
        return await pipeline.sync_all(platforms)

    async def merge(self, primary_doc_id: int, duplicate_doc_id: int) -> KnowledgeDoc | None:
        """把重复文档的来源链接迁移到主文档，并删除重复文档（含切片与索引）。"""
        if primary_doc_id == duplicate_doc_id:
            raise ValueError("主文档与重复文档不能相同")
        primary = await self.db.get(KnowledgeDoc, primary_doc_id)
        duplicate = await self.db.get(KnowledgeDoc, duplicate_doc_id)
        if primary is None or duplicate is None:
            return None

        links = (
            (await self.db.execute(select(DocSourceLink).where(DocSourceLink.doc_id == duplicate_doc_id)))
            .scalars()
        )
        for link in links:
            link.doc_id = primary_doc_id
            link.is_primary = False

        from app.retrieval.sync import deindex_document

        chunks = (await self.db.execute(select(DocChunk).where(DocChunk.doc_id == duplicate_doc_id))).scalars()
        for chunk in chunks:
            await self.db.delete(chunk)
        await self.db.delete(duplicate)
        await self.db.commit()
        await deindex_document(duplicate_doc_id)
        logger.info("source_content_merged", primary=primary_doc_id, duplicate=duplicate_doc_id)
        return primary
