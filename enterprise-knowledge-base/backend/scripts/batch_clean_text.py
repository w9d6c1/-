"""批量清洗存量文档中的 Markdown 符号（# * —）并重新分块 + 向量化

清洗范围:
  - 清理 knowledge_doc.plain_text 中的 # * > ` --- 等 Markdown 标记
  - 清理文档中嵌入的连续长破折号、代码块残留
  - 保留 **加粗** 和 1./2. 序号，保持文档层次

用法:
  docker exec kb-backend python /app/scripts/batch_clean_text.py

选项:
  --dry-run          仅预览清洗前后的变化，不写入
  --strategy         重新分块的策略 (默认 recursive)
  --chunk-size       分块大小 (默认 512)
  --chunk-overlap    重叠大小 (默认 80)
  --skip-sync        仅清洗 + 重切，不同步向量库
"""

import asyncio
import re
import sys

from sqlalchemy import select

from app.core.database import AsyncSessionLocal
from app.models.document import DocChunk, KnowledgeDoc
from app.services.chunking import chunk_content
from app.retrieval.sync import deindex_document as _deindex
from app.retrieval.sync import sync_document as _sync


def clean_plain_text(text: str) -> str:
    """清洗知识库文档纯文本中的格式符号。比 clean_response 更温和，不删换行结构。"""
    if not text:
        return text

    text = text.replace("\r\n", "\n")

    # 删除 HTML 标签残留
    text = re.sub(r"<[^>]+>", "", text)

    # 删除    残留
    text = re.sub(r"</?\s*(think|response)\s*>", "", text, flags=re.IGNORECASE)

    # 删除独立分割线行（--- *** ___ 独占行）
    text = re.sub(r"^\s*[-*_]{3,}\s*$", "", text, flags=re.MULTILINE)

    # 逐行清洗行首 Markdown 结构符号
    lines_out: list[str] = []
    for line in text.split("\n"):
        stripped = line.lstrip()
        leading = line[: len(line) - len(stripped)] if stripped else line
        if not stripped:
            lines_out.append(line)
            continue
        # 去除 # 标题标记
        cleaned = re.sub(r"^#{1,6}\s+", "", stripped)
        # 去除 > 引用
        cleaned = re.sub(r"^>\s+", "", cleaned)
        # 去除 - * 列表标记（保留 **加粗** 和 1. 2. 序号）
        cleaned = re.sub(r"^[-*]\s+", "", cleaned)
        lines_out.append(leading + cleaned)
    text = "\n".join(lines_out)

    # 删除代码块 ```...```
    text = re.sub(r"```[\s\S]*?```", "", text)

    # 删除连续长破折号 / 下划线
    text = re.sub(r"[—_]{3,}", "", text)

    # 压缩多余空行
    text = re.sub(r"\n{3,}", "\n\n", text)

    return text.strip()


def parse_args() -> dict:
    args = {
        "dry_run": False,
        "strategy": "recursive",
        "chunk_size": 512,
        "chunk_overlap": 80,
        "skip_sync": False,
    }
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


def _count_special_chars(text: str) -> dict:
    """统计需要清洗的特殊字符数量"""
    return {
        "headings": len(re.findall(r"^#{1,6}\s+", text, re.MULTILINE)),
        "list_markers": len(re.findall(r"^[-*]\s+", text, re.MULTILINE)),
        "blockquotes": len(re.findall(r"^>\s+", text, re.MULTILINE)),
        "dividers": len(re.findall(r"^\s*[-*_]{3,}\s*$", text, re.MULTILINE)),
        "long_dashes": len(re.findall(r"[—]{3,}", text)),
        "code_blocks": len(re.findall(r"```", text)),
        "think_tags": len(re.findall(r"<think|<response", text, re.IGNORECASE)),
    }


async def main() -> None:
    args = parse_args()
    strategy = args["strategy"]
    chunk_size = args["chunk_size"]
    chunk_overlap = args["chunk_overlap"]

    print(f"策略: {strategy} | chunk_size={chunk_size} tokens | chunk_overlap={chunk_overlap} tokens")
    if args["dry_run"]:
        print(">>> DRY RUN — 仅预览变化，不执行写入 <<<")
    if args["skip_sync"]:
        print(">>> SKIP SYNC — 不推送到 ES/Milvus <<<")
    print()

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(KnowledgeDoc).where(KnowledgeDoc.plain_text.isnot(None))
        )
        docs = list(result.scalars())

    if not docs:
        print("没有找到任何文档")
        return

    print(f"共 {len(docs)} 个文档\n")

    stats = {
        "total": len(docs),
        "cleaned": 0,
        "unchanged": 0,
        "rechunk_failed": 0,
        "synced": 0,
        "sync_failed": 0,
        "total_specials_removed": 0,
    }

    for doc in docs:
        label = f"[{doc.id}] {doc.title[:50]}"
        original = (doc.plain_text or "").replace("\r\n", "\n").strip()
        cleaned = clean_plain_text(original)

        if cleaned == original:
            print(f"  ○ {label} — 无需清洗")
            stats["unchanged"] += 1
            continue

        before = _count_special_chars(original)
        after = _count_special_chars(cleaned)
        removed = sum(before.values()) - sum(after.values())
        stats["total_specials_removed"] += removed

        title_tag = re.findall(r"^#{1,6}\s+", original, re.MULTILINE)
        list_tag = re.findall(r"^[-*]\s+", original, re.MULTILINE)
        dash_tag = re.findall(r"[—]{3,}", original)

        clean_details = []
        if title_tag:
            clean_details.append(f"{len(title_tag)} 个标题标记")
        if list_tag:
            clean_details.append(f"{len(list_tag)} 个列表标记")
        if dash_tag:
            clean_details.append(f"{len(dash_tag)} 处长破折号")
        detail_str = "，".join(clean_details) if clean_details else f"删除 {removed} 处符号"
        if removed == 0 and len(original) != len(cleaned):
            detail_str = f"空白规范化 (-{len(original) - len(cleaned)} 字符)"

        if args["dry_run"]:
            print(f"  ? {label} — {detail_str}")
            continue

        # 写入清洗后的文本
        try:
            async with AsyncSessionLocal() as db2:
                doc_obj = await db2.get(KnowledgeDoc, doc.id)
                if doc_obj:
                    doc_obj.plain_text = cleaned
                    doc_obj.word_count = len(cleaned)
                    await db2.commit()

            # 重新分块
            chunks = chunk_content(cleaned, strategy, chunk_size, chunk_overlap)
            new_count = len(chunks)
            old_count = doc.chunk_count or 0

            async with AsyncSessionLocal() as db3:
                existing = await db3.execute(
                    select(DocChunk).where(DocChunk.doc_id == doc.id)
                )
                for c in existing.scalars():
                    await db3.delete(c)

                doc_obj2 = await db3.get(KnowledgeDoc, doc.id)
                if doc_obj2:
                    doc_obj2.chunk_strategy = strategy
                    doc_obj2.chunk_size = chunk_size
                    doc_obj2.chunk_overlap = chunk_overlap

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
                    db3.add(ch)

                if doc_obj2:
                    doc_obj2.chunk_count = len(chunks)

                await db3.commit()

            # 同步到向量库
            if doc.status == "online" and doc.review_status == "approved" and not args["skip_sync"]:
                try:
                    await _deindex(doc.id)
                    async with AsyncSessionLocal() as db4:
                        await _sync(db4, doc.id)
                    stats["synced"] += 1
                except Exception:
                    stats["sync_failed"] += 1
                    print(f"  ⚠ {label} 清洗成功但向量同步失败 — 请手动 /resync")

            stats["cleaned"] += 1
            delta = f"分块 {old_count} → {new_count}" if old_count != new_count else f"分块保持 {new_count}"
            print(f"  ✓ {label} — {detail_str} | {delta}")

        except Exception as exc:
            stats["rechunk_failed"] += 1
            print(f"  ✗ {label} — 失败: {exc}")

    print()
    print("=" * 50)
    print(f"总计: {stats['total']} 个文档")
    print(f"  已清洗: {stats['cleaned']}")
    print(f"  无需清洗: {stats['unchanged']}")
    print(f"  分块失败: {stats['rechunk_failed']}")
    print(f"  向量同步成功: {stats['synced']}")
    print(f"  向量同步失败: {stats['sync_failed']}")
    print(f"  共清除特殊符号: {stats['total_specials_removed']} 处")
    if args["dry_run"]:
        print("  >>> DRY RUN — 未实际写入 <<<")


if __name__ == "__main__":
    asyncio.run(main())
