"""知识库文档加载器 — 对接 chunking/text_parser 生成 LangChain Document"""

from datetime import datetime

from langchain_core.documents import Document
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.document import DocChunk, KnowledgeDoc
from app.services.chunking import chunk_content
from app.services.text_parser import parse_text


class DocumentMeta:
    def __init__(
        self,
        source: str,
        scope: str = "public",
        doc_id: int = 0,
        chunk_index: int = 0,
        title: str = "",
        department: str | None = None,
        page_number: int | None = None,
        heading_path: str | None = None,
        source_type: str = "internal",
        source_name: str | None = None,
        original_url: str | None = None,
        publish_time: datetime | None = None,
    ):
        self.source = source
        self.scope = scope
        self.doc_id = doc_id
        self.chunk_index = chunk_index
        self.title = title
        self.department = department
        self.page_number = page_number
        self.heading_path = heading_path
        self.source_type = source_type
        self.source_name = source_name
        self.original_url = original_url
        self.publish_time = publish_time

    def to_langchain_meta(self) -> dict:
        return {
            "source": self.source,
            "scope": self.scope,
            "doc_id": self.doc_id,
            "chunk_index": self.chunk_index,
            "title": self.title,
            "department": self.department or "",
            "page_number": self.page_number if self.page_number else "",
            "heading_path": self.heading_path or "",
            "source_type": self.source_type or "internal",
            "source_name": self.source_name or "",
            "original_url": self.original_url or "",
            "publish_time": self.publish_time.isoformat() if self.publish_time else "",
        }


def load_text(
    content: str,
    meta: DocumentMeta,
    chunk_size: int = 512,
    chunk_overlap: int = 80,
    strategy: str = "recursive",
) -> list[Document]:
    if not content.strip():
        return []

    result = parse_text(content, meta.source.rsplit(".", 1)[-1] if "." in meta.source else "txt")
    chunks = chunk_content(result.plain_text, strategy, chunk_size, chunk_overlap)

    docs: list[Document] = []
    for i, chunk in enumerate(chunks):
        chunk_meta = DocumentMeta(
            source=meta.source,
            scope=meta.scope,
            doc_id=meta.doc_id,
            chunk_index=i,
            title=meta.title,
            department=meta.department,
            source_type=meta.source_type,
            source_name=meta.source_name,
            original_url=meta.original_url,
            publish_time=meta.publish_time,
        )
        docs.append(Document(page_content=chunk, metadata=chunk_meta.to_langchain_meta()))
    return docs


async def load_doc_chunks(db: AsyncSession, doc_id: int) -> list[Document]:
    doc = await db.get(KnowledgeDoc, doc_id)
    if doc is None:
        return []

    stmt = (
        select(DocChunk)
        .where(DocChunk.doc_id == doc_id)
        .order_by(DocChunk.chunk_index)
    )
    result = await db.execute(stmt)
    chunks = list(result.scalars())

    docs: list[Document] = []
    for ch in chunks:
        meta = DocumentMeta(
            source=f"doc:{doc_id}",
            scope=ch.scope,
            doc_id=doc.id,
            chunk_index=ch.chunk_index,
            title=doc.title or "",
            department=doc.department,
            page_number=ch.page_number,
            heading_path=ch.heading_path,
            source_type=doc.source_type,
            source_name=doc.source_name,
            original_url=doc.original_url,
            publish_time=doc.publish_time,
        )
        docs.append(Document(page_content=ch.content, metadata=meta.to_langchain_meta()))
    return docs


async def load_by_scope(
    db: AsyncSession,
    scope: str | None = None,
    limit: int = 1000,
) -> list[Document]:
    stmt = select(KnowledgeDoc).where(KnowledgeDoc.status == "online")
    if scope:
        stmt = stmt.where(KnowledgeDoc.scope == scope)
    stmt = stmt.limit(limit)

    result = await db.execute(stmt)
    docs_list = list(result.scalars())

    if not docs_list:
        return []

    doc_ids = [doc.id for doc in docs_list]
    chunks_stmt = (
        select(DocChunk)
        .where(DocChunk.doc_id.in_(doc_ids))
        .order_by(DocChunk.doc_id, DocChunk.chunk_index)
    )
    chunks_result = await db.execute(chunks_stmt)
    all_chunks = list(chunks_result.scalars())

    doc_map: dict[int, KnowledgeDoc] = {doc.id: doc for doc in docs_list}
    chunks_by_doc: dict[int, list[DocChunk]] = {}
    for ch in all_chunks:
        chunks_by_doc.setdefault(ch.doc_id, []).append(ch)

    all_docs: list[Document] = []
    for doc_id, doc in doc_map.items():
        chunks = chunks_by_doc.get(doc_id, [])
        for ch in chunks:
            meta = DocumentMeta(
                source=f"doc:{doc_id}",
                scope=ch.scope,
                doc_id=doc.id,
                chunk_index=ch.chunk_index,
                title=doc.title or "",
                department=doc.department,
                page_number=ch.page_number,
                heading_path=ch.heading_path,
                source_type=doc.source_type,
                source_name=doc.source_name,
                original_url=doc.original_url,
                publish_time=doc.publish_time,
            )
            all_docs.append(Document(page_content=ch.content, metadata=meta.to_langchain_meta()))
    return all_docs
