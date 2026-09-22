"""日志留存定时清理模块

清理规则:
  - ChatLog: 默认保留 180 天（可配 CHAT_LOG_RETENTION_DAYS）
  - OperateLog: 永久保留（不清理）
  - SecurityLog: 永久保留（不清理）

通过 lifespan 注册到 FastAPI 事件循环。
"""

import asyncio
from datetime import datetime, timedelta

from sqlalchemy import delete, text

from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.core.logging import logger


async def cleanup_expired_chat_logs() -> int:
    retention_days = settings.chat_log_retention_days
    if retention_days <= 0:
        return 0

    cutoff = datetime.utcnow() - timedelta(days=retention_days)
    try:
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                text("DELETE FROM chat_log WHERE created_at < :cutoff"),
                {"cutoff": cutoff},
            )
            await db.commit()
            deleted = result.rowcount
            if deleted > 0:
                logger.info("chat_log_cleanup", deleted_rows=deleted, retention_days=retention_days)
            return deleted
    except Exception:
        logger.warning("chat_log_cleanup_failed", exc_info=True)
        return 0


async def retention_scheduler() -> None:
    while True:
        await asyncio.sleep(86400)  # 每24小时
        try:
            await cleanup_expired_chat_logs()
        except Exception:
            logger.warning("retention_scheduler_error", exc_info=True)
