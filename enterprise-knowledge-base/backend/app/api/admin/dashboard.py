"""管理仪表盘 — 统计聚合 API"""

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import select, func

from app.core.dependencies import DbDep, require_auth
from app.models.user import User

router = APIRouter(tags=["admin-dashboard"])


@router.get("/stats")
async def dashboard_stats(
    db: DbDep,
    _u: Annotated[User, Depends(require_auth)],
) -> dict:
    from app.models.audit import ChatLog
    from app.models.document import KnowledgeDoc

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

    async def _qt1():
        r = await db.execute(select(func.count()).select_from(ChatLog).where(ChatLog.created_at >= today_start))
        return r.scalar() or 0

    async def _qt2():
        r = await db.execute(
            select(func.count()).select_from(ChatLog).where(ChatLog.created_at >= today_start, ChatLog.hit_faq_id.isnot(None))
        )
        return r.scalar() or 0

    async def _qt3():
        from app.api.admin.dictionary import Feedback
        thirty_days_ago = now - timedelta(days=30)
        r = await db.execute(
            select(func.count(), func.sum(Feedback.rating == "like").label("likes"))
            .select_from(Feedback).where(Feedback.created_at >= thirty_days_ago)
        )
        row = r.one_or_none()
        total = row[0] if row else 0
        likes = int(row[1] or 0) if row and row[1] is not None else 0
        return total, likes

    async def _qt4():
        r = await db.execute(select(func.count()).select_from(KnowledgeDoc).where(KnowledgeDoc.review_status == "pending"))
        return r.scalar() or 0

    async def _qt5():
        from app.api.admin.dictionary import UnansweredQuestion
        r = await db.execute(select(func.count()).select_from(UnansweredQuestion).where(UnansweredQuestion.status == "pending"))
        return r.scalar() or 0

    today_chats, today_faq_hit, (feedback_total, feedback_likes), pending_reviews, pending_unanswered = await asyncio.gather(
        _qt1(), _qt2(), _qt3(), _qt4(), _qt5(),
    )

    faq_hit_rate = round(today_faq_hit / today_chats, 2) if today_chats > 0 else 0.0
    feedback_good_rate = round(feedback_likes / feedback_total, 2) if feedback_total > 0 else 0.0

    trend: list[dict] = []
    for i in range(6, -1, -1):
        day = now - timedelta(days=i)
        day_start = day.replace(hour=0, minute=0, second=0, microsecond=0)
        day_end = day_start + timedelta(days=1)
        day_count_r = await db.execute(
            select(func.count()).select_from(ChatLog).where(ChatLog.created_at >= day_start, ChatLog.created_at < day_end)
        )
        trend.append({"date": day_start.strftime("%m-%d"), "count": day_count_r.scalar() or 0})

    return {
        "today_chats": today_chats,
        "faq_hit_rate": faq_hit_rate,
        "feedback_good_rate": feedback_good_rate,
        "pending_reviews": pending_reviews,
        "pending_unanswered": pending_unanswered,
        "trend": trend,
    }
