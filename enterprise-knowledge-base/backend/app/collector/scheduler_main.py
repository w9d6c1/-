"""采集服务独立调度入口 — 仅运行采集同步任务，与问答服务物理隔离。

用于 collector 独立容器（docker-compose profile=collector）。若启用本服务，
建议关闭后端调度器中的 collector_daily_sync 任务以避免重复同步。

用法（容器内，工作目录 /app）:
    python -m app.collector.scheduler_main
"""

import time

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.core.config import settings
from app.core.logging import logger
from app.services.scheduler import _run_collector_sync


def main() -> None:
    scheduler = AsyncIOScheduler()
    scheduler.add_job(
        _run_collector_sync,
        "cron",
        hour=settings.collector_sync_hour,
        minute=settings.collector_sync_minute,
        id="collector_sync",
    )
    scheduler.start()
    logger.info(
        "collector_scheduler_started",
        hour=settings.collector_sync_hour,
        minute=settings.collector_sync_minute,
    )
    print(f"采集调度已启动：每日 {settings.collector_sync_hour:02d}:{settings.collector_sync_minute:02d} 同步")
    try:
        while True:
            time.sleep(3600)
    except (KeyboardInterrupt, SystemExit):
        scheduler.shutdown()


if __name__ == "__main__":
    main()
