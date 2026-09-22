"""采集编排 pipeline 测试（fake 采集器 + mock sync_document）"""

import pytest
from unittest.mock import AsyncMock, patch

from sqlalchemy import select

from app.collector.base import BaseCollector
from app.collector.models import RawArticle
from app.collector.pipeline import CollectorPipeline
from app.models.collector import CollectorSyncLog, CollectorSyncState


def _article(external_id: str, content: str, platform: str = "wechat") -> RawArticle:
    return RawArticle(
        platform=platform,
        external_id=external_id,
        title=f"文章{external_id}",
        html_content=f"<p>{content}</p>",
        original_url=f"https://example.com/{external_id}",
    )


class FakeCollector(BaseCollector):
    """单页采集器：首次返回 (articles, cursor)，之后返回空页表示拉取完毕"""

    platform = "wechat"

    def __init__(self, articles, cursor=None, fail_times=0):
        self.articles = articles
        self.cursor = cursor
        self.fail_times = fail_times
        self.calls = 0
        self._served = False

    async def fetch_since(self, cursor):
        self.calls += 1
        if self.calls <= self.fail_times:
            raise RuntimeError("fetch boom")
        if self._served:
            return [], None
        self._served = True
        return self.articles, self.cursor


class PagedFakeCollector(BaseCollector):
    """多页采集器：按序返回预设页面 [(articles, cursor), ...]"""

    platform = "wechat"

    def __init__(self, pages):
        self.pages = list(pages)
        self.cursors_received = []

    async def fetch_since(self, cursor):
        self.cursors_received.append(cursor)
        return self.pages.pop(0)


@pytest.fixture
def pipeline(db_session):
    return CollectorPipeline(db_session, category_id=1, retry_base_delay=0)


class TestSyncPlatform:
    @pytest.mark.asyncio
    async def test_success_updates_state_and_log(self, pipeline, db_session):
        articles = [
            _article("w1", "特莱顿电渗透脉冲防潮系统通过电场作用阻止水分毛细渗透。"),
            _article("w2", "公司年度培训计划涵盖安全生产与职业技能两大模块。"),
        ]
        fake = FakeCollector(articles, cursor="cursor-abc")
        with patch("app.collector.pipeline.get_collector", return_value=fake), \
             patch("app.retrieval.sync.sync_document", new=AsyncMock(return_value=1)):
            result = await pipeline.sync_platform("wechat")

        assert result.ok
        assert result.fetched == 2
        assert result.ingested == 2

        state = (await db_session.execute(
            select(CollectorSyncState).where(CollectorSyncState.platform == "wechat")
        )).scalar_one()
        assert state.last_status == "success"
        # 全部页面拉取完毕后游标重置为 None（下次从头拉取，去重兜底）
        assert state.last_cursor is None

        log = (await db_session.execute(
            select(CollectorSyncLog).where(CollectorSyncLog.platform == "wechat")
        )).scalar_one()
        assert log.status == "success"
        assert log.ingested_count == 2

    @pytest.mark.asyncio
    async def test_failure_isolated_and_recorded(self, pipeline, db_session):
        fake = FakeCollector([], fail_times=99)
        with patch("app.collector.pipeline.get_collector", return_value=fake), \
             patch("app.retrieval.sync.sync_document", new=AsyncMock(return_value=1)):
            result = await pipeline.sync_platform("wechat")

        assert not result.ok
        assert result.error is not None
        state = (await db_session.execute(
            select(CollectorSyncState).where(CollectorSyncState.platform == "wechat")
        )).scalar_one()
        assert state.last_status == "failed"
        assert state.last_error

    @pytest.mark.asyncio
    async def test_retry_then_success(self, db_session):
        fake = FakeCollector([_article("w1", "重试后成功的内容文本。")], cursor="c", fail_times=2)
        pipeline = CollectorPipeline(db_session, category_id=1, max_retries=3, retry_base_delay=0)
        with patch("app.collector.pipeline.get_collector", return_value=fake), \
             patch("app.retrieval.sync.sync_document", new=AsyncMock(return_value=1)):
            result = await pipeline.sync_platform("wechat")
        assert result.ok
        # 2 次失败重试 + 第 1 页 + 空尾页
        assert fake.calls == 4

    @pytest.mark.asyncio
    async def test_cursor_passed_and_advanced(self, db_session):
        db_session.add(CollectorSyncState(platform="wechat", last_cursor="prev-cursor", last_status="success"))
        await db_session.commit()

        fake = FakeCollector([_article("w1", "增量同步游标传递测试内容。")], cursor="new-cursor")
        captured: list = []
        original = fake.fetch_since

        async def capture(cursor):
            captured.append(cursor)
            return await original(cursor)

        fake.fetch_since = capture
        pipeline = CollectorPipeline(db_session, category_id=1, retry_base_delay=0)
        with patch("app.collector.pipeline.get_collector", return_value=fake), \
             patch("app.retrieval.sync.sync_document", new=AsyncMock(return_value=1)):
            await pipeline.sync_platform("wechat")

        # 首页从已存游标开始，第二页（空尾页）从 new-cursor 继续
        assert captured == ["prev-cursor", "new-cursor"]
        state = (await db_session.execute(
            select(CollectorSyncState).where(CollectorSyncState.platform == "wechat")
        )).scalar_one()
        # 尾页游标为 None → 全部拉完，游标重置
        assert state.last_cursor is None


class TestPagination:
    @pytest.mark.asyncio
    async def test_fetches_all_pages_until_cursor_none(self, db_session):
        """一次同步循环拉取全部页面，直到游标为 None"""
        pages = [
            ([_article("p1", "第一页第一篇文章内容。"), _article("p2", "第一页第二篇文章内容。")], "2"),
            ([_article("p3", "第二页第一篇文章内容。"), _article("p4", "第二页第二篇文章内容。")], "4"),
            ([_article("p5", "第三页第一篇文章内容。")], None),
        ]
        fake = PagedFakeCollector(pages)
        pipeline = CollectorPipeline(db_session, category_id=1, retry_base_delay=0)
        with patch("app.collector.pipeline.get_collector", return_value=fake), \
             patch("app.retrieval.sync.sync_document", new=AsyncMock(return_value=1)):
            result = await pipeline.sync_platform("wechat")

        assert result.ok
        assert result.fetched == 5
        assert result.ingested == 5
        assert fake.cursors_received == [None, "2", "4"]

        state = (await db_session.execute(
            select(CollectorSyncState).where(CollectorSyncState.platform == "wechat")
        )).scalar_one()
        assert state.last_status == "success"
        assert state.last_cursor is None

    @pytest.mark.asyncio
    async def test_stops_at_max_pages_and_keeps_cursor(self, db_session):
        """达到页数上限时停止，保留游标供下次继续"""
        pages = [
            ([_article("p1", "第一页文章内容。")], "20"),
            ([_article("p2", "第二页文章内容。")], "40"),
            ([_article("p3", "第三页文章内容。")], None),
        ]
        fake = PagedFakeCollector(pages)
        pipeline = CollectorPipeline(db_session, category_id=1, retry_base_delay=0, max_pages=2)
        with patch("app.collector.pipeline.get_collector", return_value=fake), \
             patch("app.retrieval.sync.sync_document", new=AsyncMock(return_value=1)):
            result = await pipeline.sync_platform("wechat")

        assert result.ok
        assert result.fetched == 2
        assert fake.cursors_received == [None, "20"]

        state = (await db_session.execute(
            select(CollectorSyncState).where(CollectorSyncState.platform == "wechat")
        )).scalar_one()
        assert state.last_cursor == "40"

    @pytest.mark.asyncio
    async def test_page_delay_between_pages(self, db_session):
        """适配器级页间延时：collector.page_delay > 0 时翻页之间休眠"""
        pages = [
            ([_article("p1", "第一页文章内容。")], "2"),
            ([_article("p2", "第二页文章内容。")], None),
        ]
        fake = PagedFakeCollector(pages)
        fake.page_delay = 1.5
        pipeline = CollectorPipeline(db_session, category_id=1, retry_base_delay=0)
        with patch("app.collector.pipeline.get_collector", return_value=fake), \
             patch("app.retrieval.sync.sync_document", new=AsyncMock(return_value=1)), \
             patch("app.collector.pipeline.asyncio.sleep", new=AsyncMock()) as sleep_mock:
            result = await pipeline.sync_platform("wechat")

        assert result.ok
        sleep_mock.assert_awaited_once_with(1.5)

    @pytest.mark.asyncio
    async def test_continues_from_saved_cursor(self, db_session):
        """从上次保存的游标继续拉取"""
        db_session.add(CollectorSyncState(platform="wechat", last_cursor="20", last_status="success"))
        await db_session.commit()

        fake = PagedFakeCollector([([_article("p2", "第二页文章内容。")], None)])
        pipeline = CollectorPipeline(db_session, category_id=1, retry_base_delay=0)
        with patch("app.collector.pipeline.get_collector", return_value=fake), \
             patch("app.retrieval.sync.sync_document", new=AsyncMock(return_value=1)):
            result = await pipeline.sync_platform("wechat")

        assert result.ok
        assert fake.cursors_received == ["20"]
        state = (await db_session.execute(
            select(CollectorSyncState).where(CollectorSyncState.platform == "wechat")
        )).scalar_one()
        assert state.last_cursor is None


class TestSyncAll:
    @pytest.mark.asyncio
    async def test_isolates_platform_failures(self, db_session):
        good = FakeCollector([_article("w1", "微信平台正常同步的内容。", platform="wechat")], cursor="c1")
        bad = FakeCollector([], fail_times=99)

        def fake_get(platform):
            return good if platform == "wechat" else bad

        pipeline = CollectorPipeline(db_session, category_id=1, max_retries=0, retry_base_delay=0)
        with patch("app.collector.pipeline.get_collector", side_effect=fake_get), \
             patch("app.retrieval.sync.sync_document", new=AsyncMock(return_value=1)):
            summary = await pipeline.sync_all(["wechat", "toutiao"])

        assert not summary.all_ok
        assert summary.failed_platforms == ["toutiao"]
        wechat = next(r for r in summary.results if r.platform == "wechat")
        assert wechat.ok
        assert wechat.ingested == 1
        assert summary.total_ingested == 1
