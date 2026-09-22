"""单元测试 — 发布调度器失败路径（B2：rollback 后不再直接写过期实例）"""

from unittest.mock import patch

import pytest

from app.articles.models import PublishingRecord
from app.articles.schedule import _execute_scheduled_publishes


class _Record:
    def __init__(self):
        self.id = 1
        self.article_id = 1
        self.platform = "zhihu"
        self.status = "pending"
        self.account_id = 1
        self.scheduled_at = None
        self.error_message = None


class _Article:
    id = 1
    title = "标题"
    content = "正文"
    image_placement = None


class _Account:
    id = 1
    account_group = "2113"
    ws_token = "enc"
    credentials = None


class _ScalarsResult:
    def __init__(self, records=None, scalar=None):
        self._records = records
        self._scalar = scalar

    def scalars(self):
        return self

    def all(self):
        return self._records or []

    def scalar(self):
        return self._scalar


class _FakeSession:
    def __init__(self):
        self.record = _Record()
        self.execute_count = 0
        self.committed = 0
        self.rolled_back = 0

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def execute(self, stmt):
        self.execute_count += 1
        if self.execute_count == 1:
            return _ScalarsResult(records=[self.record])
        if self.execute_count == 2:
            return _ScalarsResult(scalar=_Article())
        return _ScalarsResult(scalar=_Account())

    async def commit(self):
        self.committed += 1

    async def rollback(self):
        self.rolled_back += 1

    async def get(self, model, pk):
        assert model is PublishingRecord
        return self.record


class TestScheduledPublishFailure:
    @pytest.mark.asyncio
    async def test_publish_exception_marks_record_failed(self):
        """发布抛异常时，rollback 后经 db.get 重新拉取并标记 failed，不直接写过期实例"""
        session = _FakeSession()

        with patch("app.articles.schedule.AsyncSessionLocal", lambda: session), patch(
            "app.articles.publisher.publish_via_bridge", side_effect=RuntimeError("boom")
        ), patch("app.articles.crypto.decrypt_credentials", return_value="tok"):
            await _execute_scheduled_publishes()

        assert session.record.status == "failed"
        assert "boom" in (session.record.error_message or "")
        assert session.rolled_back >= 1
        assert session.committed >= 2
