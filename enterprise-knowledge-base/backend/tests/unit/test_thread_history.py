"""线程历史恢复测试 — thread_history 服务 + /api/agent/threads 路由（TDD）"""

import itertools
from datetime import datetime

import pytest

from app.models.audit import ChatLog


_seq = itertools.count(1)


def _log(thread_id, source, question, answer="答", user_id=None, citations=None, created=None):
    return ChatLog(
        id=next(_seq),
        thread_id=thread_id,
        request_id=f"req-{thread_id}-{question}",
        source=source,
        user_id=user_id,
        question=question,
        answer=answer,
        node_status="success",
        confidence=0.9,
        node_output={"citations": citations} if citations else None,
        created_at=created or datetime.now(),
    )


class TestThreadHistoryService:
    @pytest.mark.asyncio
    async def test_list_threads_grouped_and_ordered(self, db_session):
        from app.services.thread_history import list_threads

        db_session.add_all([
            _log("t1", "internal", "第一问", user_id=1, created=datetime(2026, 8, 1, 10, 0)),
            _log("t1", "internal", "第二问", user_id=1, created=datetime(2026, 8, 1, 11, 0)),
            _log("t2", "internal", "新线程问", user_id=1, created=datetime(2026, 8, 2, 9, 0)),
            _log("t3", "internal", "他人线程", user_id=2, created=datetime(2026, 8, 3, 9, 0)),
            _log("t4", "customer", "客服问", created=datetime(2026, 8, 3, 9, 0)),
        ])
        await db_session.commit()

        threads = await list_threads(db_session, "internal", user_id=1)
        assert [t["thread_id"] for t in threads] == ["t2", "t1"]
        assert threads[1]["turns"] == 2
        assert threads[1]["title"] == "第一问"

    @pytest.mark.asyncio
    async def test_get_thread_messages_order_and_citations(self, db_session):
        from app.services.thread_history import get_thread_messages

        cites = [{"index": 1, "title": "知乎文章", "platform": "zhihu", "url": "https://z", "source_name": "知乎", "is_internal": False}]
        db_session.add_all([
            _log("t1", "internal", "问一", "答一", user_id=1, created=datetime(2026, 8, 1, 10, 0)),
            _log("t1", "internal", "问二", "答二", user_id=1, citations=cites, created=datetime(2026, 8, 1, 10, 5)),
        ])
        await db_session.commit()

        msgs = await get_thread_messages(db_session, "t1", "internal", user_id=1)
        assert [m["question"] for m in msgs] == ["问一", "问二"]
        assert msgs[1]["citations"] == cites
        assert msgs[0]["citations"] is None

    @pytest.mark.asyncio
    async def test_messages_user_isolation(self, db_session):
        from app.services.thread_history import get_thread_messages

        db_session.add(_log("t-other", "internal", "他人问题", user_id=2))
        await db_session.commit()
        assert await get_thread_messages(db_session, "t-other", "internal", user_id=1) == []


class TestThreadsAPI:
    @pytest.mark.asyncio
    async def test_list_requires_auth(self, client):
        resp = await client.get("/api/agent/threads")
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_list_and_messages_with_auth(self, client, db_session, token_factory):
        token = await token_factory("threaduser", role="operator")
        from app.models.user import User
        from sqlalchemy import select

        uid = (await db_session.execute(select(User.id).where(User.username == "threaduser"))).scalar_one()
        db_session.add_all([
            _log("ta", "internal", "我的问题", "我的答案", user_id=uid),
            _log("tb", "internal", "别人问题", user_id=uid + 1000),
        ])
        await db_session.commit()

        headers = {"Authorization": f"Bearer {token}"}
        resp = await client.get("/api/agent/threads", headers=headers)
        assert resp.status_code == 200
        ids = [t["thread_id"] for t in resp.json()]
        assert ids == ["ta"]

        resp = await client.get("/api/agent/threads/ta/messages", headers=headers)
        assert resp.status_code == 200
        assert resp.json()[0]["question"] == "我的问题"

        resp = await client.get("/api/agent/threads/tb/messages", headers=headers)
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_customer_messages_public(self, client, db_session):
        db_session.add(_log("tc", "customer", "客服问题", "客服答案"))
        await db_session.commit()
        resp = await client.get("/api/agent/threads/tc/messages", params={"source": "customer"})
        assert resp.status_code == 200
        assert resp.json()[0]["answer"] == "客服答案"
