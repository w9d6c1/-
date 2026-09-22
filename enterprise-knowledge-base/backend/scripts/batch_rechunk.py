"""批量重建所有存量文档分块 — 用新分块策略重新切分 + 向量化

用法:
  docker exec kb-backend python /app/scripts/batch_rechunk.py

选项:
  --dry-run    仅预览，不执行
  --strategy   分块策略 (默认 recursive)
  --chunk-size 分块大小 (默认 512)
  --chunk-overlap 重叠大小 (默认 80)
  --skip-sync  仅重切不分块，不同步向量库
"""

import asyncio
import sys
from datetime import datetime, timezone

from sqlalchemy import select

from app.core.database import AsyncSessionLocal
from app.models.document import DocChunk, KnowledgeDoc
from app.services.chunking import chunk_content
from app.retrieval.sync import deindex_document as _deindex
from app.retrieval.sync import sync_document as _sync


def parse_args() -> dict:
    args = {"dry_run": False, "strategy": "recursive", "chunk_size": 512, "chunk_overlap": 80, "skip_sync": False}
    for a in sys.argv[1:]:
        if a == "--dry-run":
            args["dry_run"] = True
        elif a == "--skip-sync":
            args["skip_sync"] = True
        elif a.startswith("--strategy="):
            args["strategy"] = a.split("=", 1)[1]
        elif a.startswith("--chunk-size="):
            args["chunk_size"] = int(a.split("=", 1)[1])
        elif a.startswith("--chunk-overlap="):
            args["chunk_overlap"] = int(a.split("=", 1)[1])
    return args


async def main() -> None:
    args = parse_args()
    strategy = args["strategy"]
    chunk_size = args["chunk_size"]
    chunk_overlap = args["chunk_overlap"]

    print(f"策略: {strategy} | chunk_size={chunk_size} tokens | chunk_overlap={chunk_overlap} tokens")
    if args["dry_run"]:
        print(">>> DRY RUN — 只预览，不执行 <<<")
    print()

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(KnowledgeDoc).where(KnowledgeDoc.plain_text.isnot(None))
        )
        docs = list(result.scalars())

    if not docs:
        print("没有找到任何文档")
        return

    print(f"共 {len(docs)} 个文档待处理\n")

    stats = {"total": len(docs), "success": 0, "failed": 0, "chunk_changes": []}

    for doc in docs:
        label = f"[{doc.id}] {doc.title[:40]}"
        old_count = doc.chunk_count

        if args["dry_run"]:
            chunks = chunk_content(doc.plain_text or "", strategy, chunk_size, chunk_overlap)
            new_count = len(chunks)
            delta = f" {old_count} → {new_count}"
            stats["chunk_changes"].append((doc.id, old_count, new_count))
        else:
            try:
                chunks = chunk_content(doc.plain_text or "", strategy, chunk_size, chunk_overlap)
                new_count = len(chunks)

                async with AsyncSessionLocal() as db2:
                    existing = await db2.execute(
                        select(DocChunk).where(DocChunk.doc_id == doc.id)
                    )
                    for c in existing.scalars():
                        await db2.delete(c)

                    doc_obj = await db2.get(KnowledgeDoc, doc.id)
                    if doc_obj:
                        doc_obj.chunk_strategy = strategy
                        doc_obj.chunk_size = chunk_size
                        doc_obj.chunk_overlap = chunk_overlap

                    from app.services.document_service import (
                        _clean_metadata_from_content,
                        _extract_heading_path,
                        _extract_page_number,
                    )

                    for i, text in enumerate(chunks):
                        page_num = _extract_page_number(text)
                        heading = _extract_heading_path(text)
                        clean_text = _clean_metadata_from_content(text)
                        ch = DocChunk(
                            doc_id=doc.id,
                            chunk_index=i,
                            content=clean_text,
                            scope=doc.scope,
                            page_number=page_num,
                            heading_path=heading,
                        )
                        db2.add(ch)

                    if doc_obj:
                        doc_obj.chunk_count = len(chunks)

                    await db2.commit()

                if doc.status == "online" and doc.review_status == "approved":
                    try:
                        await _deindex(doc.id)
                        async with AsyncSessionLocal() as db3:
                            await _sync(db3, doc.id)
                    except Exception:
                        print(f"  ⚠ {label} 重向量化失败 — 请手动调用 /resync")

                delta = f" {old_count} → {new_count}"
                stats["chunk_changes"].append((doc.id, old_count, new_count))
                stats["success"] += 1
            except Exception as exc:
                delta = " FAILED"
                stats["failed"] += 1
                print(f"  ✗ {label}{delta} — {exc}")

        print(f"  {'✓' if not args['dry_run'] else '?'} {label}{delta}")

    print()
    print(f"完成: {stats['success']} 成功 / {stats['failed']} 失败")
    print()
    print("切块变化:")
    for doc_id, old, new in stats["chunk_changes"]:
        direction = "↑" if new > old else "↓" if new < old else "="
        print(f"  文档 {doc_id}: {old} {direction} {new}")


if __name__ == "__main__":
    asyncio.run(main())
