"""文档管理业务逻辑层"""

import asyncio
import json
import re
from dataclasses import asdict

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import defer

from app.core.logging import logger
from app.models.document import DocChunk, KnowledgeDoc
from app.models.user import User
from app.schemas.document import DocumentCreate, DocumentUpdate
from app.services.chunking import chunk_content
from app.services.text_cleaner import CleanResult, clean_document_text
from app.services.text_cleaner_llm import llm_enhance_clean
from app.services.text_parser import parse_text


class DocumentService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def list(
        self,
        current_user: User,
        page: int = 1,
        page_size: int = 20,
        category_id: int | None = None,
        scope: str | None = None,
        status: str | None = None,
    ) -> tuple[list[KnowledgeDoc], int]:
        stmt = select(KnowledgeDoc).options(defer(KnowledgeDoc.plain_text))
        if current_user.role != "superadmin" and current_user.department:
            stmt = stmt.where(KnowledgeDoc.department == current_user.department)
        if category_id:
            stmt = stmt.where(KnowledgeDoc.category_id == category_id)
        if scope:
            stmt = stmt.where(KnowledgeDoc.scope == scope)
        if status:
            stmt = stmt.where(KnowledgeDoc.status == status)

        count_stmt = select(func.count()).select_from(stmt.subquery())
        total = (await self.db.execute(count_stmt)).scalar() or 0

        stmt = stmt.order_by(KnowledgeDoc.id.desc())
        stmt = stmt.offset((page - 1) * page_size).limit(page_size)
        result = await self.db.execute(stmt)
        items = list(result.scalars())
        return items, total

    async def create(self, payload: DocumentCreate, current_user: User) -> KnowledgeDoc:
        doc = KnowledgeDoc(
            category_id=payload.category_id,
            title=payload.title,
            scope=payload.scope,
            chunk_strategy=payload.chunk_strategy,
            chunk_size=payload.chunk_size,
            chunk_overlap=payload.chunk_overlap,
            department=payload.department or current_user.department,
            file_type="txt",
            file_path="",
        )
        self.db.add(doc)
        try:
            await self.db.commit()
        except Exception:
            await self.db.rollback()
            raise
        await self.db.refresh(doc)
        return doc

    async def update_content(
        self,
        doc_id: int,
        content: str,
        file_type: str,
        current_user: User,
        auto_clean: bool = True,
    ) -> KnowledgeDoc | None:
        doc = await self.db.get(KnowledgeDoc, doc_id)
        if doc is None:
            return None
        if current_user.role != "superadmin" and doc.department != current_user.department:
            raise PermissionError

        doc.raw_text = content
        if auto_clean:
            clean_result = clean_document_text(content)
            parse_source = clean_result.text
            doc.clean_status = "cleaned"
            doc.clean_report = json.dumps(asdict(clean_result.report), ensure_ascii=False)
        else:
            parse_source = content
            doc.clean_status = "skipped"
            doc.clean_report = None

        result = parse_text(parse_source, file_type)
        doc.file_type = file_type
        doc.plain_text = result.plain_text
        doc.word_count = result.word_count
        try:
            await self.db.commit()
        except Exception:
            await self.db.rollback()
            raise
        await self.db.refresh(doc)
        await self.chunk(doc_id, current_user)
        return doc

    async def clean(
        self, doc_id: int, current_user: User, use_llm: bool = False
    ) -> tuple[KnowledgeDoc, CleanResult] | None:
        """清洗已有文档：优先用 raw_text 重建，无原文则直接清洗 plain_text。

        use_llm=True 时叠加 LLM 增强（未配置/失败自动回退规则结果）。
        返回 (doc, clean_result)；文档不存在返回 None；无内容抛 ValueError。
        """
        doc = await self.db.get(KnowledgeDoc, doc_id)
        if doc is None:
            return None
        if current_user.role != "superadmin" and doc.department != current_user.department:
            raise PermissionError

        if doc.raw_text:
            source = doc.raw_text
            rebuild_via_parse = True
        elif doc.plain_text:
            source = doc.plain_text
            rebuild_via_parse = False
        else:
            raise ValueError("文档无内容，无法清洗")

        clean_result = await llm_enhance_clean(source, use_llm=use_llm)
        if rebuild_via_parse and doc.file_type not in ("pdf", "docx"):
            # 与上传流程一致：仅 md/txt 走 parse_text；pdf/docx 保留行结构
            parsed = parse_text(clean_result.text, doc.file_type)
            doc.plain_text = parsed.plain_text
            doc.word_count = parsed.word_count
        else:
            doc.plain_text = clean_result.text
            doc.word_count = len(clean_result.text)

        doc.clean_status = "cleaned"
        doc.clean_report = json.dumps(asdict(clean_result.report), ensure_ascii=False)
        try:
            await self.db.commit()
        except Exception:
            await self.db.rollback()
            raise
        await self.db.refresh(doc)
        await self.chunk(doc_id, current_user)
        return doc, clean_result

    async def chunk(self, doc_id: int, current_user: User) -> dict:
        doc = await self.db.get(KnowledgeDoc, doc_id)
        if doc is None or doc.plain_text is None:
            return {"chunk_count": 0}
        if current_user.role != "superadmin" and doc.department != current_user.department:
            raise PermissionError
        existing = await self.db.execute(select(DocChunk).where(DocChunk.doc_id == doc_id))
        for c in existing.scalars():
            await self.db.delete(c)
        chunks = chunk_content(
            doc.plain_text, doc.chunk_strategy, doc.chunk_size, doc.chunk_overlap
        )
        for i, text in enumerate(chunks):
            page_num = _extract_page_number(text)
            heading = _extract_heading_path(text)
            clean_text = _clean_metadata_from_content(text)
            ch = DocChunk(
                doc_id=doc.id, chunk_index=i, content=clean_text, scope=doc.scope,
                page_number=page_num, heading_path=heading,
            )
            self.db.add(ch)
        doc.chunk_count = len(chunks)
        await self.db.commit()
        await self.db.refresh(doc)
        return {"chunk_count": len(chunks)}

    async def review(self, doc_id: int, action: str, current_user: User, comment: str | None = None) -> KnowledgeDoc | None:
        doc = await self.db.get(KnowledgeDoc, doc_id)
        if doc is None:
            return None
        if current_user.role not in ("superadmin", "dept_admin"):
            raise PermissionError
        if doc.review_status != "pending":
            raise ValueError("Only pending documents can be reviewed")
        if action == "approve":
            doc.review_status = "approved"
            doc.status = "online"
            doc.reviewer_id = current_user.id
            doc.review_comment = comment
        elif action == "reject":
            doc.review_status = "rejected"
            doc.status = "draft"
            doc.reviewer_id = current_user.id
            doc.review_comment = comment
        await self.db.commit()
        await self.db.refresh(doc)
        if action == "approve":
            asyncio.create_task(_sync_document_async(doc_id))
        return doc

    async def delete(self, doc_id: int, current_user: User) -> bool:
        doc = await self.db.get(KnowledgeDoc, doc_id)
        if doc is None:
            return False
        if current_user.role != "superadmin" and doc.department != current_user.department:
            raise PermissionError
        await self.db.delete(doc)
        await self.db.commit()
        asyncio.create_task(_deindex_document_async(doc_id))
        return True


async def _sync_document_async(doc_id: int) -> None:
    from app.core.database import AsyncSessionLocal
    from app.retrieval.sync import sync_document

    for attempt in range(3):
        try:
            async with AsyncSessionLocal() as db:
                await sync_document(db, doc_id)
            return
        except Exception:
            logger.warning("document_sync_failed", doc_id=doc_id, attempt=attempt + 1, exc_info=True)
            if attempt < 2:
                await asyncio.sleep(2 ** attempt)


async def _deindex_document_async(doc_id: int) -> None:
    from app.retrieval.sync import deindex_document

    for attempt in range(3):
        try:
            await deindex_document(doc_id)
            return
        except Exception:
            logger.warning("document_deindex_failed", doc_id=doc_id, attempt=attempt + 1, exc_info=True)
            if attempt < 2:
                await asyncio.sleep(2 ** attempt)


_PAGE_MARKER = re.compile(r"^\[P\d+\]\s*", re.MULTILINE)
_HEADING_PATH_RE = re.compile(r"(?:^|(?<=\n))(#{1,3})\s+(.+?)(?:\n|$)")


def _extract_page_number(text: str) -> int | None:
    m = _PAGE_MARKER.search(text)
    if m:
        digits = re.search(r"\d+", m.group())
        if digits:
            return int(digits.group())
    return None


def _extract_heading_path(text: str) -> str | None:
    headings = _HEADING_PATH_RE.findall(text)
    if not headings:
        return None
    parts: list[str] = []
    for _level, title in headings:
        clean_title = title.strip().rstrip("#").strip()
        if clean_title:
            parts.append(clean_title)
    return " > ".join(parts) if parts else None


def _clean_metadata_from_content(text: str) -> str:
    text = _PAGE_MARKER.sub("", text)
    return text.strip()
