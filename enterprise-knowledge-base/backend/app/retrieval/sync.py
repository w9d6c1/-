"""向量同步服务 — 文档 chunks → ES BM25 + Milvus Dense"""

from datetime import UTC, datetime

from langchain_core.documents import Document
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.embedding import embed_texts
from app.models.category import KnowledgeCategory
from app.models.document import DocChunk, KnowledgeDoc
from app.retrieval.es_client import (
    create_bm25_index,
    ensure_source_type_mapping,
    index_documents,
)
from app.retrieval.es_client import (
    delete_doc_from_all_scopes as es_delete_all,
)
from app.retrieval.milvus_client import (
    delete_doc_from_all_scopes as mv_delete_all,
)
from app.retrieval.milvus_client import (
    insert_vectors,
)


async def _category_effectively_disabled(db: AsyncSession, category_id: int | None) -> bool:
    """分类自身或其任一祖先被禁用时，视为禁用 — 禁用分类下的知识不可被检索"""
    cursor = category_id
    visited: set[int] = set()
    while cursor is not None and cursor not in visited:
        visited.add(cursor)
        category = await db.get(KnowledgeCategory, cursor)
        if category is None:
            return False
        if category.status == "disabled":
            return True
        cursor = category.parent_id
    return False


async def _collect_subtree_category_ids(db: AsyncSession, root_id: int) -> set[int]:
    """收集分类及其所有子孙分类的 id"""
    ids: set[int] = {root_id}
    frontier = [root_id]
    while frontier:
        stmt = select(KnowledgeCategory.id).where(KnowledgeCategory.parent_id.in_(frontier))
        children = [row[0] for row in (await db.execute(stmt)).all()]
        new_ids = [cid for cid in children if cid not in ids]
        ids.update(new_ids)
        frontier = new_ids
    return ids


async def sync_document(db: AsyncSession, doc_id: int) -> int:
    doc = await db.get(KnowledgeDoc, doc_id)
    if doc is None or doc.status != "online":
        return 0
    if doc.review_status != "approved":
        return 0
    if await _category_effectively_disabled(db, doc.category_id):
        return 0

    stmt = select(DocChunk).where(DocChunk.doc_id == doc_id).order_by(DocChunk.chunk_index)
    result = await db.execute(stmt)
    chunks = list(result.scalars())
    if not chunks:
        return 0

    scope = doc.scope or "public"
    await create_bm25_index(scope)
    await ensure_source_type_mapping(scope)

    lc_docs: list[Document] = []
    texts: list[str] = []
    for ch in chunks:
        lc_docs.append(Document(
            page_content=ch.content,
            metadata={
                "doc_id": doc.id,
                "chunk_index": ch.chunk_index,
                "scope": scope,
                "title": doc.title or "",
                "department": doc.department or "",
                "page_number": ch.page_number if ch.page_number else "",
                "heading_path": ch.heading_path or "",
                "source_type": doc.source_type or "internal",
                "source_name": doc.source_name or "",
                "original_url": doc.original_url or "",
                "publish_time": doc.publish_time.isoformat() if doc.publish_time else "",
            },
        ))
        texts.append(ch.content)

    embeddings = await embed_texts(texts)

    es_count = await index_documents(lc_docs)
    mv_count = await insert_vectors(lc_docs, embeddings, scope)

    now = datetime.now(UTC)
    for _, ch in enumerate(chunks):
        ch.vector_id = f"{doc_id}_{ch.chunk_index}"
        ch.bm25_id = f"{doc_id}_{ch.chunk_index}"
        ch.last_sync_at = now
    try:
        await db.commit()
    except Exception:
        await db.rollback()
        raise

    return es_count + mv_count


async def deindex_document(doc_id: int) -> int:
    es_deleted = await es_delete_all(doc_id)
    mv_deleted = await mv_delete_all(doc_id)
    return es_deleted + mv_deleted


async def sync_all_online(db: AsyncSession) -> int:
    stmt = select(KnowledgeDoc).where(KnowledgeDoc.status == "online")
    result = await db.execute(stmt)
    docs = list(result.scalars())
    total = 0
    for doc in docs:
        total += await sync_document(db, doc.id)
    return total


async def deindex_category(db: AsyncSession, category_id: int) -> int:
    """禁用/删除分类时，将该分类及其子孙分类下的文档全部下线索引，返回处理文档数"""
    cat_ids = await _collect_subtree_category_ids(db, category_id)
    stmt = select(KnowledgeDoc.id).where(KnowledgeDoc.category_id.in_(cat_ids))
    doc_ids = [row[0] for row in (await db.execute(stmt)).all()]
    for doc_id in doc_ids:
        await deindex_document(doc_id)
    return len(doc_ids)


async def resync_category(db: AsyncSession, category_id: int) -> int:
    """重新启用分类时，重新为该分类及其子孙分类下的在线文档建立索引"""
    cat_ids = await _collect_subtree_category_ids(db, category_id)
    stmt = select(KnowledgeDoc.id).where(
        KnowledgeDoc.category_id.in_(cat_ids), KnowledgeDoc.status == "online"
    )
    doc_ids = [row[0] for row in (await db.execute(stmt)).all()]
    total = 0
    for doc_id in doc_ids:
        total += await sync_document(db, doc_id)
    return total
