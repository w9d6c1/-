"""线程历史服务 — 从 chat_log 重建线程列表与问答序列（刷新后恢复会话）。"""

from sqlalchemy import func, select

from app.models.audit import ChatLog


async def list_threads(
    db,
    source: str,
    user_id: int | None = None,
    limit: int = 50,
) -> list[dict]:
    """按 thread_id 分组返回线程摘要，按最近活跃倒序。

    user_id 非空时仅返回该用户的线程（internal 隔离）。
    """
    stmt = (
        select(
            ChatLog.thread_id,
            func.min(ChatLog.id).label("first_id"),
            func.count().label("turns"),
            func.max(ChatLog.created_at).label("last_active"),
        )
        .where(ChatLog.source == source)
        .group_by(ChatLog.thread_id)
        .order_by(func.max(ChatLog.created_at).desc(), ChatLog.thread_id)
        .limit(limit)
    )
    if user_id is not None:
        stmt = stmt.where(ChatLog.user_id == user_id)
    rows = (await db.execute(stmt)).all()
    if not rows:
        return []

    first_ids = [r.first_id for r in rows]
    qstmt = select(ChatLog.id, ChatLog.question).where(ChatLog.id.in_(first_ids))
    titles = {r.id: r.question for r in (await db.execute(qstmt)).all()}

    return [
        {
            "thread_id": r.thread_id,
            "title": (titles.get(r.first_id) or "")[:20] or "历史对话",
            "turns": int(r.turns),
            "last_active": r.last_active,
        }
        for r in rows
    ]


async def get_thread_messages(
    db,
    thread_id: str,
    source: str,
    user_id: int | None = None,
) -> list[dict]:
    """按时间升序返回线程问答序列；user_id 非空时做归属过滤。"""
    stmt = (
        select(ChatLog)
        .where(ChatLog.thread_id == thread_id, ChatLog.source == source)
        .order_by(ChatLog.id.asc())
    )
    if user_id is not None:
        stmt = stmt.where(ChatLog.user_id == user_id)
    rows = (await db.execute(stmt)).scalars().all()
    return [
        {
            "question": r.question,
            "answer": r.answer or "",
            "confidence": r.confidence,
            "faq_hit": r.hit_faq_id is not None,
            "citations": (r.node_output or {}).get("citations"),
            "images": (r.node_output or {}).get("images"),
            "created_at": r.created_at,
        }
        for r in rows
    ]
