"""照片标签重新分析回填脚本 — 用最新打标签规则（防编造版）重打照片库全部照片的 tags/description。

用法:
  docker exec kb-backend python /app/scripts/backfill_photo_tags.py [--limit N] [--after-id N] [--dry-run] [--interval 0.5] [--only-empty]

说明:
- 需配置 VISION_MODEL_API_KEY，否则退出。
- 建议始终带 --only-empty（只处理空标签照片），并先 --dry-run 预览范围。
- 逐张下载 MinIO 照片 → 视觉模型按新规则重打标签/描述 → 写库。
- 防误删：若新分析结果标签与描述均为空，则不覆盖已有标签。
- 故障保护：连续 MAX_CONSECUTIVE_FAILURES 张分析失败即中止，避免视觉接口故障期间批量覆盖。
- 幂等可续传：--after-id 从指定 id 之后继续。
"""

import asyncio
import sys

from sqlalchemy import func, or_, select

from app.articles.models import Photo
from app.articles.photo_service import PhotoService, _PHOTO_BUCKET
from app.articles.vision import get_vision_provider
from app.core.database import AsyncSessionLocal
from app.core.minio_client import get_minio_client

# 连续分析失败达到该阈值即中止（疑似视觉接口故障）
MAX_CONSECUTIVE_FAILURES = 5


def parse_args() -> dict:
    args = {"limit": None, "after_id": 0, "dry_run": False, "interval": 1.5, "only_empty": False}
    for a in sys.argv[1:]:
        if a.startswith("--limit="):
            args["limit"] = int(a.split("=", 1)[1])
        elif a.startswith("--after-id="):
            args["after_id"] = int(a.split("=", 1)[1])
        elif a == "--dry-run":
            args["dry_run"] = True
        elif a.startswith("--interval="):
            args["interval"] = float(a.split("=", 1)[1])
        elif a == "--only-empty":
            args["only_empty"] = True
    return args


async def _analyze_with_retry(svc, data, filename, max_attempts: int = 4) -> tuple:
    """调用视觉模型打标签；对限流/瞬时错误做指数退避重试。

    失败签名是 ([], filename)，可据此判断本次调用未真正成功。
    """
    for attempt in range(max_attempts):
        tags, description = await svc._analyze_photo(data, filename)
        if tags or (description and description != filename):
            return tags, description
        if attempt < max_attempts - 1:
            delay = min(10 * (2 ** attempt), 120)
            print(f"    分析未成功，{delay}s 后重试（第 {attempt + 2}/{max_attempts} 次）...")
            await asyncio.sleep(delay)
    return [], filename


async def main() -> None:
    args = parse_args()
    provider = get_vision_provider()
    if provider is None:
        print("未配置 VISION_MODEL_API_KEY，无法重打标签，退出。")
        return

    minio_client = get_minio_client()
    svc = PhotoService.__new__(PhotoService)  # 仅复用 _analyze_photo（不依赖 self.db）

    async with AsyncSessionLocal() as db:
        stmt = select(Photo).order_by(Photo.id.asc())
        if args["only_empty"]:
            empty = func.coalesce(func.json_length(Photo.tags), 0) == 0
            stmt = stmt.where(or_(Photo.tags.is_(None), empty))
        if args["after_id"]:
            stmt = stmt.where(Photo.id > args["after_id"])
        if args["limit"]:
            stmt = stmt.limit(args["limit"])
        photos = list((await db.execute(stmt)).scalars().all())

    if not photos:
        print("没有需要重打标签的照片。")
        return
    print(f"待重打照片 {len(photos)} 张（起始 id={photos[0].id}，结束 id={photos[-1].id}）")
    if args["dry_run"]:
        print("DRY-RUN：跳过实际执行")
        return

    stats = {"done": 0, "failed": 0, "skipped": 0}
    consecutive_failures = 0
    for photo in photos:
        try:
            resp = minio_client.get_object(_PHOTO_BUCKET, photo.object_name)
            data = resp.read()
            resp.close()
            resp.release_conn()

            tags, description = await _analyze_with_retry(svc, data, photo.filename)
            # 重试后仍失败（tags 空且描述==文件名），保留原标签不覆盖
            if not tags and (not description or description == photo.filename):
                consecutive_failures += 1
                stats["skipped"] += 1
                print(f"  - 照片 {photo.id} 重打失败/无可识别内容，保留原标签")
                if consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
                    print(
                        f"  连续 {consecutive_failures} 张分析失败，疑似视觉接口故障，中止执行。"
                        f" 已完成：成功 {stats['done']}，失败 {stats['failed']}，保留原样 {stats['skipped']}"
                    )
                    return
                continue
            consecutive_failures = 0

            async with AsyncSessionLocal() as db:
                p = await db.get(Photo, photo.id)
                if not p:
                    stats["skipped"] += 1
                    continue
                p.tags = tags
                p.description = description
                await db.commit()

            stats["done"] += 1
            print(f"  ✓ 照片 {photo.id} tags={tags}")
            await asyncio.sleep(args["interval"])
        except Exception as exc:
            consecutive_failures += 1
            stats["failed"] += 1
            print(f"  ✗ 照片 {photo.id} 失败: {exc}")
            if consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
                print(
                    f"  连续 {consecutive_failures} 张失败，疑似视觉接口故障，中止执行。"
                    f" 已完成：成功 {stats['done']}，失败 {stats['failed']}，保留原样 {stats['skipped']}"
                )
                return

    print(
        f"\n完成：成功 {stats['done']}，失败 {stats['failed']}，保留原样 {stats['skipped']}"
    )


if __name__ == "__main__":
    asyncio.run(main())
