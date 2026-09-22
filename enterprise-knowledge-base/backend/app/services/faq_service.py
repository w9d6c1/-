"""FAQ 业务逻辑层"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import logger
from app.models.faq import KnowledgeFAQ
from app.models.user import User
from app.schemas.faq import FAQCreate, FAQBulkImport, FAQUpdate


async def _incremental_refresh_single_faq(db: AsyncSession, faq_id: int) -> None:
    """增量刷新单条 FAQ：在线则 upsert，否则 remove。复用 load_online_faqs 的生效期过滤逻辑。"""
    from app.agents.nodes.faq import remove_faq_vector, upsert_faq_vector

    faq = await db.get(KnowledgeFAQ, faq_id)
    if faq is None:
        await remove_faq_vector(faq_id)
        return

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    is_online = (
        faq.status == "online"
        and faq.review_status == "approved"
        and not (faq.effective_start and faq.effective_start > now)
        and not (faq.effective_end and faq.effective_end < now)
    )

    if not is_online:
        await remove_faq_vector(faq_id)
        return

    questions = [faq.question]
    if faq.similar_questions:
        questions.extend(faq.similar_questions)
    await upsert_faq_vector({
        "id": faq.id,
        "question": faq.question,
        "answer": faq.answer,
        "scope": faq.scope,
        "questions_for_embedding": questions,
    })


async def _schedule_incremental_refresh(faq_id: int) -> None:
    """后台任务：用独立会话增量刷新单条 FAQ 向量（约 ~30ms）。"""
    try:
        from app.core.database import AsyncSessionLocal

        async with AsyncSessionLocal() as db:
            await _incremental_refresh_single_faq(db, faq_id)
    except Exception:
        logger.info("faq_incremental_refresh_skipped")


async def load_online_faqs(
    db: AsyncSession,
    scopes: list[str] | None = None,
) -> list[dict]:
    """加载在线 FAQ，过滤生效期"""
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    stmt = select(KnowledgeFAQ).where(
        KnowledgeFAQ.status == "online",
        KnowledgeFAQ.review_status == "approved",
    )
    result = await db.execute(stmt)
    rows = result.scalars().all()

    faqs: list[dict] = []
    for faq in rows:
        if scopes and faq.scope not in scopes:
            continue
        if faq.effective_start and faq.effective_start > now:
            continue
        if faq.effective_end and faq.effective_end < now:
            continue

        questions = [faq.question]
        if faq.similar_questions:
            questions.extend(faq.similar_questions)

        faqs.append({
            "id": faq.id,
            "question": faq.question,
            "answer": faq.answer,
            "scope": faq.scope,
            "questions_for_embedding": questions,
        })
    return faqs


class FAQService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def list(self, current_user: User, page: int = 1, page_size: int = 20) -> tuple[list[KnowledgeFAQ], int]:
        from sqlalchemy import func

        count_stmt = select(func.count()).select_from(KnowledgeFAQ)
        stmt = select(KnowledgeFAQ).order_by(KnowledgeFAQ.id.desc())
        if current_user.role != "superadmin" and current_user.department:
            count_stmt = count_stmt.where(KnowledgeFAQ.department == current_user.department)
            stmt = stmt.where(KnowledgeFAQ.department == current_user.department)
        total_r = await self.db.execute(count_stmt)
        total = total_r.scalar() or 0
        offset = (page - 1) * page_size
        stmt = stmt.offset(offset).limit(page_size)
        result = await self.db.execute(stmt)
        items = list(result.scalars())
        return items, total

    async def create(self, payload: FAQCreate, current_user: User) -> KnowledgeFAQ:
        faq = KnowledgeFAQ(
            category_id=payload.category_id,
            question=payload.question,
            similar_questions=payload.similar_questions,
            answer=payload.answer,
            tags=payload.tags,
            scope=payload.scope,
            department=payload.department or current_user.department,
            effective_start=payload.effective_start,
            effective_end=payload.effective_end,
        )
        self.db.add(faq)
        try:
            await self.db.commit()
        except Exception:
            await self.db.rollback()
            raise
        await self.db.refresh(faq)
        asyncio.create_task(_schedule_incremental_refresh(faq.id))
        return faq

    async def bulk_import(self, payload: FAQBulkImport, current_user: User) -> int:
        count = 0
        for item in payload.items:
            faq = KnowledgeFAQ(
                category_id=item.category_id,
                question=item.question,
                similar_questions=item.similar_questions,
                answer=item.answer,
                tags=item.tags,
                scope=item.scope,
                department=item.department or current_user.department,
                effective_start=item.effective_start,
                effective_end=item.effective_end,
            )
            self.db.add(faq)
            count += 1
        try:
            await self.db.commit()
        except Exception:
            await self.db.rollback()
            raise
        # 批量导入的条目均为 draft/pending，不在线，无需刷新向量索引；
        # 审核通过 (approve) 时会各自触发单条增量刷新。
        return count

    async def delete(self, faq_id: int, current_user: User) -> bool:
        faq = await self.db.get(KnowledgeFAQ, faq_id)
        if faq is None:
            return False
        if current_user.role != "superadmin" and faq.department != current_user.department:
            raise PermissionError
        await self.db.delete(faq)
        try:
            await self.db.commit()
        except Exception:
            await self.db.rollback()
            raise
        asyncio.create_task(_schedule_incremental_refresh(faq_id))
        return True

    async def submit_for_review(self, faq_id: int, current_user: User) -> KnowledgeFAQ | None:
        faq = await self.db.get(KnowledgeFAQ, faq_id)
        if faq is None:
            return None
        if current_user.role != "superadmin" and faq.department != current_user.department:
            raise PermissionError
        if faq.status not in ("draft", "offline"):
            raise ValueError("Only draft or offline FAQs can be submitted for review")
        faq.review_status = "pending"
        faq.status = "draft"
        try:
            await self.db.commit()
        except Exception:
            await self.db.rollback()
            raise
        await self.db.refresh(faq)
        return faq

    async def approve(self, faq_id: int, current_user: User) -> KnowledgeFAQ | None:
        faq = await self.db.get(KnowledgeFAQ, faq_id)
        if faq is None:
            return None
        if current_user.role not in ("superadmin", "dept_admin"):
            raise PermissionError
        if faq.review_status != "pending":
            raise ValueError("Only pending FAQs can be approved")
        faq.review_status = "approved"
        faq.status = "online"
        faq.reviewer_id = current_user.id
        try:
            await self.db.commit()
        except Exception:
            await self.db.rollback()
            raise
        await self.db.refresh(faq)
        asyncio.create_task(_schedule_incremental_refresh(faq.id))
        return faq

    async def reject(self, faq_id: int, current_user: User, comment: str | None = None) -> KnowledgeFAQ | None:
        faq = await self.db.get(KnowledgeFAQ, faq_id)
        if faq is None:
            return None
        if current_user.role not in ("superadmin", "dept_admin"):
            raise PermissionError
        if faq.review_status != "pending":
            raise ValueError("Only pending FAQs can be rejected")
        faq.review_status = "rejected"
        faq.status = "draft"
        faq.reviewer_id = current_user.id
        faq.review_comment = comment
        try:
            await self.db.commit()
        except Exception:
            await self.db.rollback()
            raise
        await self.db.refresh(faq)
        return faq

    async def snapshot_version(self, faq_id: int, current_user_id: int) -> None:
        from app.models.faq_version import FAQVersion

        faq = await self.db.get(KnowledgeFAQ, faq_id)
        if faq is None:
            return
        snapshot = FAQVersion(
            faq_id=faq.id,
            version=faq.version,
            question=faq.question,
            answer=faq.answer,
            similar_questions=faq.similar_questions,
            tags=faq.tags,
            scope=faq.scope,
            status=faq.status,
            effective_start=faq.effective_start,
            effective_end=faq.effective_end,
            created_by=current_user_id,
        )
        self.db.add(snapshot)

    async def update(
        self, faq_id: int, payload: FAQUpdate, current_user: User
    ) -> KnowledgeFAQ | None:
        faq = await self.db.get(KnowledgeFAQ, faq_id)
        if faq is None:
            return None
        if current_user.role != "superadmin" and faq.department != current_user.department:
            raise PermissionError

        if payload.status is not None:
            if payload.status == "online" and faq.review_status != "approved":
                raise ValueError("Cannot set status to online without approval")
            faq.status = payload.status

        has_change = any(
            getattr(payload, field, None) is not None
            for field in (
                "category_id", "question", "similar_questions", "answer",
                "tags", "scope", "department",
                "effective_start", "effective_end",
            )
        )
        if has_change or payload.status is not None:
            await self.snapshot_version(faq_id, current_user.id)

        for field in (
            "category_id", "question", "similar_questions", "answer",
            "tags", "scope", "department",
            "effective_start", "effective_end",
        ):
            value = getattr(payload, field, None)
            if value is not None:
                setattr(faq, field, value)
        if has_change or payload.status is not None:
            faq.version += 1
        try:
            await self.db.commit()
        except Exception:
            await self.db.rollback()
            raise
        await self.db.refresh(faq)
        asyncio.create_task(_schedule_incremental_refresh(faq.id))
        return faq

    async def get_versions(self, faq_id: int) -> list[dict]:
        from app.models.faq_version import FAQVersion

        stmt = (
            select(FAQVersion)
            .where(FAQVersion.faq_id == faq_id)
            .order_by(FAQVersion.id.desc())
        )
        result = await self.db.execute(stmt)
        rows = result.scalars().all()
        return [
            {
                "id": v.id,
                "version": v.version,
                "question": v.question,
                "answer": v.answer,
                "similar_questions": v.similar_questions,
                "tags": v.tags,
                "scope": v.scope,
                "status": v.status,
                "created_at": v.created_at,
            }
            for v in rows
        ]

    async def rollback(self, faq_id: int, version_id: int, current_user: User) -> KnowledgeFAQ | None:
        from app.models.faq_version import FAQVersion

        faq = await self.db.get(KnowledgeFAQ, faq_id)
        if faq is None:
            return None
        if current_user.role != "superadmin" and faq.department != current_user.department:
            raise PermissionError

        snapshot = await self.db.get(FAQVersion, version_id)
        if snapshot is None or snapshot.faq_id != faq_id:
            raise ValueError("Version not found")

        await self.snapshot_version(faq_id, current_user.id)

        faq.question = snapshot.question
        faq.answer = snapshot.answer
        faq.similar_questions = snapshot.similar_questions
        faq.tags = snapshot.tags
        faq.scope = snapshot.scope
        faq.version += 1
        faq.review_status = "approved"

        try:
            await self.db.commit()
        except Exception:
            await self.db.rollback()
            raise
        await self.db.refresh(faq)
        asyncio.create_task(_schedule_incremental_refresh(faq.id))
        return faq
