"""批量上传本地文档到知识库（服务器侧脚本）。

用法（backend 容器内，工作目录 /app）:
    docker compose cp uploads backend:/app/uploads
    docker compose exec backend python -m app.scripts.bulk_upload_docs /app/uploads --scope internal

行为:
    - 遍历目录下 pdf/docx/md/txt 文件
    - 解析 → 清洗 → 分块 → 建为 online + approved → 同步 ES/Milvus
    - 幂等：同标题（文件名去扩展名）已存在则跳过，--force 可覆盖
    - 单文件失败不中断，逐文件打印结果
"""

import argparse
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

_FILE_EXT_TO_TYPE = {".pdf": "pdf", ".docx": "docx", ".md": "md", ".txt": "txt"}


async def _ingest_one(db, path: str, scope: str, category_id: int, force: bool, min_chars: int = 0) -> dict:
    from sqlalchemy import select

    from app.models.document import DocChunk, KnowledgeDoc
    from app.retrieval.sync import sync_document
    from app.services.chunking import chunk_content
    from app.services.text_cleaner import clean_document_text
    from app.services.text_parser import parse_docx_bytes, parse_pdf_bytes, parse_text

    filename = os.path.basename(path)
    ext = os.path.splitext(filename)[1].lower()
    file_type = _FILE_EXT_TO_TYPE.get(ext)
    if not file_type:
        return {"file": filename, "status": "skip", "reason": "unsupported_ext"}

    title = filename.rsplit(".", 1)[0]
    if not force:
        r = await db.execute(select(KnowledgeDoc.id).where(KnowledgeDoc.title == title).limit(1))
        if r.scalar_one_or_none() is not None:
            return {"file": filename, "status": "skip", "reason": "duplicate_title"}

    with open(path, "rb") as f:
        content = f.read()
    if not content:
        return {"file": filename, "status": "skip", "reason": "empty"}

    if file_type == "pdf":
        raw_source = parse_pdf_bytes(content).plain_text
    elif file_type == "docx":
        raw_source = parse_docx_bytes(content).plain_text
    else:
        raw_source = content.decode("utf-8", errors="ignore")

    cleaned = clean_document_text(raw_source).text
    if file_type in ("pdf", "docx"):
        plain_text = cleaned
    else:
        plain_text = parse_text(cleaned, file_type).plain_text

    if min_chars > 0 and len(plain_text.strip()) < min_chars:
        return {
            "file": filename,
            "status": "error",
            "reason": f"low_text_chars={len(plain_text.strip())}",
        }

    doc = KnowledgeDoc(
        category_id=category_id,
        title=title,
        scope=scope,
        file_type=file_type,
        file_path="",
        file_size=len(content),
        plain_text=plain_text,
        word_count=len(plain_text),
        status="online",
        review_status="approved",
        source_type="internal",
    )
    db.add(doc)
    await db.commit()
    await db.refresh(doc)

    chunks = chunk_content(plain_text, "recursive", 512, 80)
    for idx, chunk_text in enumerate(chunks):
        db.add(DocChunk(doc_id=doc.id, chunk_index=idx, content=chunk_text, scope=scope))
    doc.chunk_count = len(chunks)
    await db.commit()

    synced = await sync_document(db, doc.id)
    return {"file": filename, "status": "ok", "doc_id": doc.id, "chars": len(plain_text), "chunks": len(chunks), "synced": synced}


async def run(
    directory: str,
    scope: str,
    category_id: int,
    force: bool,
    min_chars: int = 0,
    shard_idx: int = 0,
    shard_total: int = 1,
) -> None:
    from app.core.database import AsyncSessionLocal

    if not os.path.isdir(directory):
        print(f"目录不存在: {directory}")
        raise SystemExit(1)

    if shard_total < 1 or shard_idx < 0 or shard_idx >= shard_total:
        print(f"无效分片: shard_idx={shard_idx}, shard_total={shard_total}")
        raise SystemExit(1)

    files = [
        os.path.join(directory, name)
        for name in sorted(os.listdir(directory))
        if os.path.isfile(os.path.join(directory, name))
        and os.path.splitext(name)[1].lower() in _FILE_EXT_TO_TYPE
    ]
    total_all = len(files)
    if shard_total > 1:
        files = [f for i, f in enumerate(files) if i % shard_total == shard_idx]
    print(
        f"发现 {total_all} 个可导入文件，本分片 {len(files)} 个"
        f"（scope={scope}, category_id={category_id}, shard={shard_idx}/{shard_total}, min_chars={min_chars}）"
    )

    ok = skip = error = 0
    async with AsyncSessionLocal() as db:
        for path in files:
            try:
                result = await _ingest_one(db, path, scope, category_id, force, min_chars)
            except Exception as exc:  # noqa: BLE001 - 逐文件隔离，单文件失败不中断
                result = {"file": os.path.basename(path), "status": "error", "reason": str(exc)}
            print(result, flush=True)
            if result["status"] == "ok":
                ok += 1
            elif result["status"] == "skip":
                skip += 1
            else:
                error += 1

    print(f"完成：成功 {ok}，跳过 {skip}，失败 {error}", flush=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="批量上传本地文档到知识库")
    parser.add_argument("directory", help="文档目录（容器内绝对路径）")
    parser.add_argument("--scope", default="internal", choices=["public", "internal", "customer"])
    parser.add_argument("--category-id", type=int, default=1, help="分类 ID，默认 1")
    parser.add_argument("--force", action="store_true", help="跳过标题去重检查")
    parser.add_argument("--min-chars", type=int, default=0, help="正文少于该字符数则报 low_text，0 表示不限制")
    parser.add_argument("--shard-idx", type=int, default=0, help="分片序号（0 起）")
    parser.add_argument("--shard-total", type=int, default=1, help="分片总数")
    args = parser.parse_args()
    asyncio.run(run(args.directory, args.scope, args.category_id, args.force, args.min_chars, args.shard_idx, args.shard_total))


if __name__ == "__main__":
    main()
