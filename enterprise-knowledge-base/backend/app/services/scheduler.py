"""FAQ 定时上下架调度器"""

from datetime import datetime, timezone

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import select, update

from app.core.config import settings
from app.core.logging import logger
from app.models.faq import KnowledgeFAQ

scheduler = AsyncIOScheduler()


async def _check_effective_faqs() -> None:
    from app.core.database import AsyncSessionLocal

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    try:
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(KnowledgeFAQ).where(
                    KnowledgeFAQ.effective_start.isnot(None),
                    KnowledgeFAQ.effective_start <= now,
                    KnowledgeFAQ.status == "draft",
                )
            )
            to_online = result.scalars().all()
            for faq in to_online:
                faq.status = "online"
                logger.info("faq_scheduled_online", faq_id=faq.id)
            if to_online:
                await db.commit()

            result2 = await db.execute(
                select(KnowledgeFAQ).where(
                    KnowledgeFAQ.effective_end.isnot(None),
                    KnowledgeFAQ.effective_end <= now,
                    KnowledgeFAQ.status == "online",
                )
            )
            to_offline = result2.scalars().all()
            for faq in to_offline:
                faq.status = "offline"
                logger.info("faq_scheduled_offline", faq_id=faq.id)
            if to_offline:
                await db.commit()

            if to_online or to_offline:
                from app.agents.nodes.faq import refresh_faq_vectors_from_db

                await refresh_faq_vectors_from_db(db)
    except Exception:
        logger.warning("faq_schedule_check_failed", exc_info=True)


def start_scheduler() -> None:
    scheduler.add_job(_check_effective_faqs, "interval", seconds=60, id="check_effective_faqs")
    scheduler.add_job(_run_scheduled_publishes, "interval", seconds=30, id="run_scheduled_publishes")
    scheduler.add_job(
        _run_collector_sync,
        "cron",
        hour=settings.collector_sync_hour,
        minute=settings.collector_sync_minute,
        id="collector_daily_sync",
    )
    scheduler.start()
    logger.info("faq_scheduler_started")


async def _run_collector_sync() -> None:
    """每日低峰增量同步全部已注册平台（单平台故障隔离，异常不影响调度器）。"""
    try:
        from app.collector.pipeline import CollectorPipeline
        from app.core.database import AsyncSessionLocal

        async with AsyncSessionLocal() as db:
            pipeline = CollectorPipeline(db, category_id=settings.collector_default_category_id)
            summary = await pipeline.sync_all()
            logger.info(
                "collector_daily_sync_done",
                total_fetched=summary.total_fetched,
                total_ingested=summary.total_ingested,
                failed=summary.failed_platforms,
            )
    except Exception:
        logger.warning("collector_daily_sync_failed", exc_info=True)


async def _run_scheduled_publishes() -> None:
    """代理定时发布扫描，避免跨模块循环导入"""
    try:
        from app.articles.schedule import _execute_scheduled_publishes
        await _execute_scheduled_publishes()
    except Exception:
        logger.warning("scheduled_publish_job_failed", exc_info=True)


def shutdown_scheduler() -> None:
    scheduler.shutdown(wait=False)
    logger.info("faq_scheduler_shutdown")
