"""种子数据批量导入脚本

用法:
  docker compose exec backend python -m app.scripts.import_seed_data \
    --faq data/faq.csv \
    --doc data/doc.csv \
    --syn data/syn.csv

CSV 格式:
  faq.csv:   question, answer, scope, category
  doc.csv:   title, content, scope, category
  syn.csv:   word, synonyms, scope
  
自动:
  - 创建缺失的分类节点
  - 跳过已存在的重复条目
  - FAQ import → 自动触发向量刷新
  - Document import → 自动 chunk + sync
"""

import asyncio
import csv
import os
import sys
from typing import Annotated

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

_DEFAULT_CATEGORY = "未分类"


async def ensure_category(db, name: str, scope: str = "public") -> int:
    from sqlalchemy import select
    from app.models.category import KnowledgeCategory

    r = await db.execute(
        select(KnowledgeCategory.id).where(
            KnowledgeCategory.name == name
        ).limit(1)
    )
    existing = r.scalar_one_or_none()
    if existing is not None:
        return existing

    cat = KnowledgeCategory(name=name, scope=scope)
    db.add(cat)
    await db.commit()
    await db.refresh(cat)
    return cat.id


async def import_faqs(db, csv_path: str, skip_duplicates: bool = True) -> int:
    from sqlalchemy import select
    from app.models.faq import KnowledgeFAQ

    if not os.path.isfile(csv_path):
        print(f"[WARN] FAQ file not found: {csv_path}")
        return 0

    imported = 0
    with open(csv_path, encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            question = (row.get("question") or "").strip()
            answer = (row.get("answer") or "").strip()
            scope = (row.get("scope") or "public").strip()
            category_name = (row.get("category") or _DEFAULT_CATEGORY).strip()

            if not question or not answer:
                continue

            if skip_duplicates:
                r = await db.execute(
                    select(KnowledgeFAQ.id).where(
                        KnowledgeFAQ.question == question
                    ).limit(1)
                )
                if r.scalar_one_or_none() is not None:
                    continue

            cat_id = await ensure_category(db, category_name, scope)
            faq = KnowledgeFAQ(
                category_id=cat_id,
                question=question,
                answer=answer,
                scope=scope,
                status="online",
                review_status="approved",
            )
            db.add(faq)
            await db.commit()
            imported += 1

    if imported > 0:
        try:
            from app.agents.nodes.faq import refresh_faq_vectors_from_db

            await refresh_faq_vectors_from_db(db)
        except Exception as e:
            print(f"[WARN] FAQ vector refresh skipped: {e}")
    return imported


async def import_documents(
    db, csv_path: str, skip_duplicates: bool = True,
    auto_chunk: bool = True,
) -> int:
    from sqlalchemy import select
    from app.models.document import KnowledgeDoc
    from app.services.chunking import chunk_content
    from app.services.text_parser import parse_text

    if not os.path.isfile(csv_path):
        print(f"[WARN] Document file not found: {csv_path}")
        return 0

    imported = 0
    with open(csv_path, encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            title = (row.get("title") or "").strip()
            content = (row.get("content") or "").strip()
            scope = (row.get("scope") or "public").strip()
            category_name = (row.get("category") or _DEFAULT_CATEGORY).strip()

            if not title or not content:
                continue

            if skip_duplicates:
                r = await db.execute(
                    select(KnowledgeDoc.id).where(
                        KnowledgeDoc.title == title
                    ).limit(1)
                )
                if r.scalar_one_or_none() is not None:
                    continue

            cat_id = await ensure_category(db, category_name, scope)
            doc = KnowledgeDoc(
                category_id=cat_id,
                title=title,
                scope=scope,
                file_type="txt",
                file_path="",
                file_size=len(content.encode("utf-8")),
                plain_text=content,
                word_count=len(content),
            )
            db.add(doc)
            await db.commit()
            await db.refresh(doc)

            if auto_chunk:
                try:
                    chunks = chunk_content(content, strategy="recursive", chunk_size=512, chunk_overlap=80)
                    from app.models.document import DocChunk
                    for idx, chunk_text in enumerate(chunks):
                        db.add(DocChunk(
                            doc_id=doc.id, chunk_index=idx,
                            content=chunk_text, scope=doc.scope,
                        ))
                    doc.chunk_count = len(chunks)
                except Exception:
                    pass
                await db.commit()

            imported += 1

    return imported


async def import_synonyms(db, csv_path: str, skip_duplicates: bool = True) -> int:
    from sqlalchemy import select
    from app.api.admin.dictionary import Synonym

    if not os.path.isfile(csv_path):
        print(f"[WARN] Synonym file not found: {csv_path}")
        return 0

    imported = 0
    with open(csv_path, encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            word = (row.get("word") or "").strip()
            synonyms_raw = (row.get("synonyms") or "").strip()
            scope = (row.get("scope") or "public").strip()

            if not word or not synonyms_raw:
                continue

            syn_list = [s.strip() for s in synonyms_raw.split(";") if s.strip()]
            if not syn_list:
                continue

            if skip_duplicates:
                r = await db.execute(
                    select(Synonym.id).where(Synonym.word == word).limit(1)
                )
                if r.scalar_one_or_none() is not None:
                    continue

            syn = Synonym(word=word, synonyms=syn_list, scope=scope)
            db.add(syn)
            await db.commit()
            imported += 1

    return imported


async def import_seed_data(
    db,
    faq_csv: str | None = None,
    doc_csv: str | None = None,
    syn_csv: str | None = None,
    skip_duplicates: bool = True,
) -> dict:
    result: dict[str, int] = {}
    if faq_csv:
        result["faqs"] = await import_faqs(db, faq_csv, skip_duplicates)
    if doc_csv:
        result["documents"] = await import_documents(db, doc_csv, skip_duplicates)
    if syn_csv:
        result["synonyms"] = await import_synonyms(db, syn_csv, skip_duplicates)
    return result


async def _main():
    import argparse
    from app.core.database import AsyncSessionLocal

    parser = argparse.ArgumentParser(description="种子数据批量导入")
    parser.add_argument("--faq", help="FAQ CSV 路径")
    parser.add_argument("--doc", help="文档 CSV 路径")
    parser.add_argument("--syn", help="同义词 CSV 路径")
    parser.add_argument("--no-skip", action="store_true", help="不跳过重复条目")
    args = parser.parse_args()

    async with AsyncSessionLocal() as db:
        result = await import_seed_data(
            db,
            faq_csv=args.faq,
            doc_csv=args.doc,
            syn_csv=args.syn,
            skip_duplicates=not args.no_skip,
        )
        print(f"Import complete: {result}")


if __name__ == "__main__":
    asyncio.run(_main())
