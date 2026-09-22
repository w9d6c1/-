"""历史文章图片回填 — 为存量公众号/知乎文章补采正文图片（转存 MinIO + 写入 doc_image）。

用法:
  docker exec kb-backend python /app/scripts/backfill_doc_images.py [--platform all|wechat|zhihu] [--limit N] [--dry-run]

说明:
- 仅处理 source_type in (wechat, zhihu) 且尚无 doc_image 记录的文档。
- 复用采集器拉取原文 HTML（微信素材库/发布/草稿，知乎用户内容 API + 公开页全文），
  按 doc_source_link.external_id 匹配后走 image_extractor 同一套提取/转存逻辑。
- 幂等：图片按内容 hash 去重；单篇失败跳过并记录，不中断整体。
"""

import asyncio
import sys

from sqlalchemy import exists, select

from app.collector.image_extractor import extract_and_store_images
from app.collector.registry import get_collector
from app.core.database import AsyncSessionLocal
from app.models.collector import DocSourceLink
from app.models.document import DocImage, KnowledgeDoc

_PLATFORMS = ("wechat", "zhihu")
_MAX_PAGES_TOTAL = 10000


def parse_args() -> dict:
    args = {"platform": "all", "limit": None, "dry_run": False}
    for a in sys.argv[1:]:
        if a.startswith("--platform="):
            args["platform"] = a.split("=", 1)[1]
        elif a.startswith("--limit="):
            args["limit"] = int(a.split("=", 1)[1])
        elif a == "--dry-run":
            args["dry_run"] = True
    return args


async def find_docs_needing_images(platforms: list[str], limit: int | None) -> list[KnowledgeDoc]:
    async with AsyncSessionLocal() as db:
        has_images = exists().where(DocImage.doc_id == KnowledgeDoc.id)
        stmt = (
            select(KnowledgeDoc)
            .where(
                KnowledgeDoc.source_type.in_(platforms),
                KnowledgeDoc.plain_text.isnot(None),
                has_images.is_(False),
            )
            .order_by(KnowledgeDoc.id.desc())
        )
        if limit:
            stmt = stmt.limit(limit)
        return list((await db.execute(stmt)).scalars().all())


async def find_source_links(doc_ids: list[int]) -> dict[int, DocSourceLink]:
    if not doc_ids:
        return {}
    async with AsyncSessionLocal() as db:
        stmt = (
            select(DocSourceLink)
            .where(DocSourceLink.doc_id.in_(doc_ids), DocSourceLink.external_id.isnot(None))
            .order_by(DocSourceLink.is_primary.desc())
        )
        rows = (await db.execute(stmt)).scalars().all()
    out: dict[int, DocSourceLink] = {}
    for r in rows:
        out.setdefault(r.doc_id, r)
    return out


async def write_doc_images(doc_id: int, platform: str, external_id: str, html: str, original_url: str) -> int:
    """提取并转存文章图片，写入 doc_image（文档级关联，不重切分片）。返回写入数。"""
    images = await extract_and_store_images(html, platform, external_id, original_url)
    if not images:
        return 0

    added = 0
    async with AsyncSessionLocal() as db:
        stmt = select(DocImage.content_hash).where(DocImage.doc_id == doc_id)
        existing = {h for h in (await db.execute(stmt)).scalars().all()}
        seq = max(
            (await db.execute(select(DocImage.seq).where(DocImage.doc_id == doc_id))).scalars().all() or [0],
            default=0,
        )
        for img in images:
            if img.content_hash in existing:
                continue
            seq += 1
            db.add(
                DocImage(
                    doc_id=doc_id,
                    chunk_index=None,
                    seq=seq,
                    object_name=img.object_name,
                    original_url=(img.original_url or "")[:1024] or None,
                    content_hash=img.content_hash,
                    width=img.width,
                    height=img.height,
                )
            )
            existing.add(img.content_hash)
            added += 1
        await db.commit()
    return added


async def backfill_platform(platform: str, docs: list[KnowledgeDoc], dry_run: bool) -> dict:
    stats = {"matched": 0, "updated": 0, "failed": 0, "skipped": 0, "fetched": 0}
    if not docs:
        return stats

    links = await find_source_links([d.id for d in docs])
    targets: dict[str, int] = {}
    for doc in docs:
        link = links.get(doc.id)
        if link and link.external_id:
            targets[link.external_id] = doc.id
    if not targets:
        return stats

    print(f"[{platform}] 待回填文档 {len(docs)}，目标 external_id {len(targets)}")
    if dry_run:
        print(f"[{platform}] DRY-RUN：跳过实际执行")
        return stats

    collector = get_collector(platform)
    processed: set[str] = set()
    cursor = None
    total = 0
    try:
        while True:
            batch, cursor = await collector.fetch_since(cursor)
            total += len(batch)
            for article in batch:
                if not article.external_id or article.external_id in processed:
                    continue
                processed.add(article.external_id)
                doc_id = targets.get(article.external_id)
                if doc_id is None:
                    continue
                stats["matched"] += 1
                try:
                    added = await write_doc_images(
                        doc_id, platform, article.external_id, article.html_content, article.original_url
                    )
                    stats["updated"] += 1 if added else 0
                    print(f"  ✓ doc {doc_id}（{article.title[:40]}）新增 {added} 张")
                except Exception as exc:
                    stats["failed"] += 1
                    print(f"  ✗ doc {doc_id}（{article.title[:40]}）失败: {exc}")
            if cursor is None:
                break
            if len(processed) >= len(targets):
                break
            if total > _MAX_PAGES_TOTAL:
                print(f"[{platform}] 达到拉取上限 {_MAX_PAGES_TOTAL} 条，提前终止")
                break
    finally:
        try:
            await collector.aclose()
        except Exception:
            pass
    stats["fetched"] = total
    stats["skipped"] = len(targets) - stats["matched"]
    return stats


async def main() -> None:
    args = parse_args()
    platforms = [args["platform"]] if args["platform"] != "all" else list(_PLATFORMS)
    for p in platforms:
        if p not in _PLATFORMS:
            print(f"不支持的平台: {p}")
            return

    docs = await find_docs_needing_images(platforms, args["limit"])
    by_platform: dict[str, list[KnowledgeDoc]] = {}
    for d in docs:
        by_platform.setdefault(d.source_type, []).append(d)
    print(f"待回填文档总数: {len(docs)}（{', '.join(f'{p}:{len(v)}' for p, v in by_platform.items())}）")

    totals = {"matched": 0, "updated": 0, "failed": 0, "skipped": 0, "fetched": 0}
    for platform in platforms:
        try:
            stats = await backfill_platform(platform, by_platform.get(platform, []), args["dry_run"])
        except Exception as exc:
            print(f"[{platform}] 平台级失败: {exc}")
            stats = {"matched": 0, "updated": 0, "failed": 0, "skipped": 0, "fetched": 0}
            stats["skipped"] = len(by_platform.get(platform, []))
        for k in totals:
            totals[k] += stats[k]

    print()
    print("回填完成:")
    print(f"  拉取文章: {totals['fetched']}")
    print(f"  匹配命中: {totals['matched']}")
    print(f"  成功补图: {totals['updated']}")
    print(f"  未命中:   {totals['skipped']}")
    print(f"  失败:     {totals['failed']}")


if __name__ == "__main__":
    asyncio.run(main())
