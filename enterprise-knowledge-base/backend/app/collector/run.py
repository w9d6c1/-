"""采集服务独立运行入口 — 同步全部（或指定）平台后退出。

用于 collector 容器或手动触发；与问答服务物理隔离，定时低峰运行。

用法（容器内，工作目录 /app）:
    python -m app.collector.run                  # 同步全部已注册平台
    python -m app.collector.run wechat toutiao   # 仅同步指定平台
"""

import asyncio
import sys

from app.collector.pipeline import CollectorPipeline
from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.core.logging import logger


async def run(platforms: list[str] | None = None) -> int:
    async with AsyncSessionLocal() as db:
        pipeline = CollectorPipeline(db, category_id=settings.collector_default_category_id)
        summary = await pipeline.sync_all(platforms)
    logger.info(
        "collector_run_done",
        total_fetched=summary.total_fetched,
        total_ingested=summary.total_ingested,
        failed=summary.failed_platforms,
    )
    print(
        f"同步完成：抓取 {summary.total_fetched}，入库 {summary.total_ingested}，"
        f"失败平台 {summary.failed_platforms or '无'}"
    )
    return 0 if summary.all_ok else 1


def main() -> None:
    platforms = sys.argv[1:] or None
    raise SystemExit(asyncio.run(run(platforms)))


if __name__ == "__main__":
    main()
