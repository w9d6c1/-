"""采集编排 — fetch → clean → dedup → ingest，单平台故障隔离 + 重试 + 状态/日志。

每个平台独立同步，单平台异常不影响其余平台；同步游标与状态持久化于
collector_sync_state，每次同步明细记录于 collector_sync_log。
"""

import asyncio
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.collector.cleaner import clean_html_with_images, strip_image_placeholders
from app.collector.image_extractor import extract_and_store_images
from app.collector.ingestion import (
    ACTION_CREATED,
    ACTION_MERGED,
    IngestOutcome,
    SourceContentService,
)
from app.collector.models import PlatformSyncResult, RawArticle, SyncSummary
from app.collector.registry import available_platforms, get_collector
from app.core.config import settings
from app.core.logging import logger
from app.models.collector import CollectorSyncLog, CollectorSyncState

# _set_state 游标参数哨兵：区分"未提供"（保留原值）与显式传 None（重置）
_CURSOR_UNSET = object()


class CollectorPipeline:
    def __init__(
        self,
        db: AsyncSession,
        *,
        category_id: int,
        max_retries: int = 2,
        retry_base_delay: float = 1.0,
        max_pages: int | None = None,
    ) -> None:
        self.db = db
        self.category_id = category_id
        self.max_retries = max_retries
        self.retry_base_delay = retry_base_delay
        self.max_pages = (
            max_pages if max_pages is not None else settings.collector_max_pages_per_sync
        )

    async def sync_all(self, platforms: list[str] | None = None) -> SyncSummary:
        """同步全部（或指定）平台；单平台故障被隔离，不影响其余平台。"""
        targets = platforms or available_platforms()
        summary = SyncSummary()
        for platform in targets:
            summary.results.append(await self.sync_platform(platform))
        return summary

    async def sync_platform(self, platform: str) -> PlatformSyncResult:
        """同步单个平台，维护同步状态与日志，异常被捕获并记录。"""
        result = PlatformSyncResult(platform=platform)
        log = await self._start_log(platform)
        await self._set_state(platform, status="running")
        try:
            collector = get_collector(platform)
            cursor = await self._get_cursor(platform)
            articles, final_cursor = await self._fetch_all_pages(collector, cursor)
            result.fetched = len(articles)

            ingestion = SourceContentService(self.db)
            for article in articles:
                outcome = await self._process_article(ingestion, article)
                if outcome.action == ACTION_CREATED:
                    result.ingested += 1
                elif outcome.action == ACTION_MERGED:
                    result.duplicated += 1
                else:
                    result.skipped += 1

            # final_cursor 为 None 表示全部页面拉取完毕，显式重置游标
            await self._set_state(platform, status="success", cursor=final_cursor)
            await self._finish_log(log, result, status="success")
            logger.info(
                "collector_sync_platform_ok",
                platform=platform,
                fetched=result.fetched,
                ingested=result.ingested,
                duplicated=result.duplicated,
            )
        except Exception as exc:
            result.error = str(exc)
            try:
                await self.db.rollback()
            except Exception:
                pass
            await self._set_state(platform, status="failed", error=str(exc))
            await self._finish_log(log, result, status="failed", error=str(exc))
            logger.warning("collector_sync_platform_failed", platform=platform, exc_info=True)
        return result

    async def _process_article(
        self, ingestion: SourceContentService, article: RawArticle
    ) -> IngestOutcome:
        text_with_imgs, image_count = clean_html_with_images(article.html_content)
        plain_text = strip_image_placeholders(text_with_imgs)

        images = None
        if image_count and not await ingestion.has_source_link(article.platform, article.external_id):
            images = await extract_and_store_images(
                article.html_content,
                article.platform,
                article.external_id,
                article.original_url,
            ) or None

        return await ingestion.ingest(
            article,
            plain_text,
            category_id=self.category_id,
            image_text=text_with_imgs if image_count else None,
            images=images,
            raw_html=article.html_content,
        )

    async def _fetch_all_pages(
        self, collector, cursor: str | None
    ) -> tuple[list[RawArticle], str | None]:
        """循环翻页拉取，直到游标为 None（拉完）或达到页数上限。

        返回 (全部文章, 最终游标)。最终游标为 None 表示本次已全部拉完；
        非 None 表示因页数上限中止，下次同步从该游标继续。
        """
        articles: list[RawArticle] = []
        pages = 0
        while pages < self.max_pages:
            batch, new_cursor = await self._fetch_with_retry(collector, cursor)
            articles.extend(batch)
            pages += 1
            if new_cursor is None:
                return articles, None
            cursor = new_cursor
            delay = getattr(collector, "page_delay", 0.0)
            if delay > 0:
                await asyncio.sleep(delay)
        return articles, cursor

    async def _fetch_with_retry(
        self, collector, cursor: str | None
    ) -> tuple[list[RawArticle], str | None]:
        last_error: Exception | None = None
        for attempt in range(self.max_retries + 1):
            try:
                return await collector.fetch_since(cursor)
            except Exception as exc:
                last_error = exc
                if attempt < self.max_retries:
                    await asyncio.sleep(self.retry_base_delay * (2**attempt))
        assert last_error is not None
        raise last_error

    async def _get_cursor(self, platform: str) -> str | None:
        state = await self._get_state(platform)
        return state.last_cursor if state else None

    async def _get_state(self, platform: str) -> CollectorSyncState | None:
        stmt = select(CollectorSyncState).where(CollectorSyncState.platform == platform)
        return (await self.db.execute(stmt)).scalar_one_or_none()

    async def _set_state(
        self,
        platform: str,
        *,
        status: str,
        cursor: object = _CURSOR_UNSET,
        error: str | None = None,
    ) -> None:
        state = await self._get_state(platform)
        now = datetime.now()
        if state is None:
            state = CollectorSyncState(
                platform=platform,
                last_status=status,
                last_sync_at=now,
                last_cursor=None if cursor is _CURSOR_UNSET else cursor,
                last_error=error,
            )
            self.db.add(state)
        else:
            state.last_status = status
            state.last_sync_at = now
            state.last_error = error
            if cursor is not _CURSOR_UNSET:
                state.last_cursor = cursor
        await self.db.commit()

    async def _start_log(self, platform: str) -> CollectorSyncLog:
        log = CollectorSyncLog(platform=platform, status="running")
        self.db.add(log)
        await self.db.commit()
        await self.db.refresh(log)
        return log

    async def _finish_log(
        self,
        log: CollectorSyncLog,
        result: PlatformSyncResult,
        *,
        status: str,
        error: str | None = None,
    ) -> None:
        log.finished_at = datetime.now()
        log.fetched_count = result.fetched
        log.ingested_count = result.ingested
        log.duplicated_count = result.duplicated
        log.status = status
        log.error = error
        await self.db.commit()
