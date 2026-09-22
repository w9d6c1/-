"""平台采集适配器测试 — mock HTTP 层，验证响应解析与游标（真实联调待凭证）"""

import pytest
from datetime import datetime
from unittest.mock import AsyncMock

from app.collector.http_base import parse_publish_time
from app.collector.registry import available_platforms, get_collector


class TestRegistry:
    def test_all_platforms_registered(self):
        platforms = set(available_platforms())
        assert {"wechat", "toutiao", "official_website", "zhihu", "bilibili"} <= platforms

    def test_get_collector_instance(self):
        assert get_collector("wechat").platform == "wechat"
        assert get_collector("bilibili").platform == "bilibili"

    def test_unknown_platform_raises(self):
        with pytest.raises(KeyError):
            get_collector("nonexistent")


class TestParsePublishTime:
    def test_timestamp(self):
        assert parse_publish_time(1700000000) == datetime.fromtimestamp(1700000000)

    def test_iso_string(self):
        assert parse_publish_time("2026-07-31T10:00:00") == datetime(2026, 7, 31, 10, 0, 0)

    def test_invalid_values(self):
        assert parse_publish_time("not-a-date") is None
        assert parse_publish_time(None) is None
        assert parse_publish_time(0) is None


def _material_item(media_id="m1", title="文章", url="https://mp.weixin.qq.com/s/abc",
                   update_time=1700000000, create_time=None):
    content = {"news_item": [{"title": title, "content": "<p>内容</p>", "url": url}]}
    if create_time is not None:
        content["create_time"] = create_time
    return {"media_id": media_id, "update_time": update_time, "content": content}


class TestWechatCollector:
    @pytest.mark.asyncio
    async def test_starts_from_material_source(self):
        """初始游标为 None 时从素材库（含早期群发文章）开始拉取"""
        from app.collector.adapters.wechat import WechatCollector

        c = WechatCollector()
        c._access_token = "fake-token"
        c._post_json = AsyncMock(return_value={
            "total_count": 40,
            "item": [_material_item(create_time=1699990000)],
        })
        articles, new_cursor = await c.fetch_since(None)
        assert "batchget_material" in c._post_json.call_args.args[0]
        assert len(articles) == 1
        assert articles[0].platform == "wechat"
        # external_id 用 URL（与存量链接格式一致，保证跨源去重）
        assert articles[0].external_id == "https://mp.weixin.qq.com/s/abc"
        assert articles[0].original_url == "https://mp.weixin.qq.com/s/abc"
        # 发布时间优先取素材 create_time
        assert articles[0].publish_time == datetime.fromtimestamp(1699990000)
        assert new_cursor == "material:20"

    @pytest.mark.asyncio
    async def test_material_falls_back_to_update_time(self):
        from app.collector.adapters.wechat import WechatCollector

        c = WechatCollector()
        c._access_token = "fake"
        c._post_json = AsyncMock(return_value={
            "total_count": 40,
            "item": [_material_item(update_time=1638273785)],
        })
        articles, _ = await c.fetch_since("material:0")
        assert articles[0].publish_time == datetime.fromtimestamp(1638273785)

    @pytest.mark.asyncio
    async def test_material_to_freepublish_transition(self):
        """素材库拉完后游标切换到 freepublish（发布）源"""
        from app.collector.adapters.wechat import WechatCollector

        c = WechatCollector()
        c._access_token = "fake"
        c._post_json = AsyncMock(return_value={
            "total_count": 21,
            "item": [_material_item()],
        })
        # offset=20 页返回最后 1 条（20+1 >= 21）→ 素材库拉完，切换发布源
        articles, new_cursor = await c.fetch_since("material:20")
        assert len(articles) == 1
        assert new_cursor == "freepublish:0"

    @pytest.mark.asyncio
    async def test_freepublish_pagination(self):
        from app.collector.adapters.wechat import WechatCollector

        c = WechatCollector()
        c._access_token = "fake"
        c._post_json = AsyncMock(return_value={
            "total_count": 40,
            "item": [{"media_id": "m1", "update_time": 1700000000,
                      "content": {"news_item": [{"title": "t", "content": "c", "url": "u1"}]}}],
        })
        articles, new_cursor = await c.fetch_since("freepublish:0")
        assert "freepublish" in c._post_json.call_args.args[0]
        assert len(articles) == 1
        assert new_cursor == "freepublish:20"

    @pytest.mark.asyncio
    async def test_freepublish_no_more_pages_goes_to_draft(self):
        from app.collector.adapters.wechat import WechatCollector

        c = WechatCollector()
        c._access_token = "fake"
        c._post_json = AsyncMock(return_value={
            "total_count": 1,
            "item": [{"media_id": "m1", "update_time": 1700000000,
                      "content": {"news_item": [{"title": "t", "content": "c", "url": "u"}]}}],
        })
        articles, new_cursor = await c.fetch_since("freepublish:0")
        assert len(articles) == 1
        assert new_cursor == "draft:0"

    @pytest.mark.asyncio
    async def test_material_without_url_uses_media_id(self):
        from app.collector.adapters.wechat import WechatCollector

        c = WechatCollector()
        c._access_token = "fake"
        c._post_json = AsyncMock(return_value={
            "total_count": 40,
            "item": [_material_item(media_id="m77", url="")],
        })
        articles, _ = await c.fetch_since("material:0")
        assert articles[0].external_id == "m77:0"

    @pytest.mark.asyncio
    async def test_draft_source_parses_and_ends(self):
        from app.collector.adapters.wechat import WechatCollector

        c = WechatCollector()
        c._access_token = "fake"
        c._post_json = AsyncMock(return_value={
            "total_count": 1,
            "item": [{
                "media_id": "d1",
                "update_time": 1752900000,
                "content": {
                    "create_time": 1752800000,
                    "news_item": [{"title": "草稿文章", "content": "<p>草稿内容</p>", "url": ""}],
                },
            }],
        })
        articles, new_cursor = await c.fetch_since("draft:0")
        assert "draft" in c._post_json.call_args.args[0]
        assert len(articles) == 1
        assert articles[0].title == "草稿文章"
        # 草稿 external_id 用 media_id（预览 URL 是临时链接不可靠）
        assert articles[0].external_id == "draft:d1:0"
        assert articles[0].publish_time == datetime.fromtimestamp(1752800000)
        assert new_cursor is None

    @pytest.mark.asyncio
    async def test_draft_pagination(self):
        from app.collector.adapters.wechat import WechatCollector

        c = WechatCollector()
        c._access_token = "fake"
        c._post_json = AsyncMock(return_value={
            "total_count": 42,
            "item": [{
                "media_id": "d1",
                "update_time": 1752900000,
                "content": {"news_item": [{"title": "t", "content": "c", "url": ""}]},
            }],
        })
        articles, new_cursor = await c.fetch_since("draft:0")
        assert len(articles) == 1
        assert new_cursor == "draft:20"


class TestToutiaoCollector:
    @pytest.mark.asyncio
    async def test_parses_list(self):
        from app.collector.adapters.toutiao import ToutiaoCollector

        c = ToutiaoCollector()
        c._get_json = AsyncMock(return_value={
            "data": {"list": [{"id": 100, "title": "头条文章", "content": "<p>x</p>", "url": "https://toutiao.com/100", "publish_time": 1700000000}], "has_more": True}
        })
        articles, new_cursor = await c.fetch_since(None)
        assert len(articles) == 1
        assert articles[0].platform == "toutiao"
        assert articles[0].external_id == "100"
        assert new_cursor == "2"


def _zh_item(ctype="article", id_="123", title="知乎文章", summary="<p>摘要</p>", created=1700000000):
    url = (
        f"https://zhuanlan.zhihu.com/p/{id_}"
        if ctype == "article"
        else f"https://www.zhihu.com/answer/{id_}"
    )
    return {
        "ContentType": ctype,
        "Url": url,
        "CreatedAt": created,
        "LikeCount": 1,
        "CommentCount": 2,
        "FavoriteCount": 3,
        "Title": title,
        "Summary": summary,
    }


def _zh_envelope(items, is_end=True, next_offset=None, totals=1):
    return {
        "Code": 0,
        "Message": "success",
        "Data": {
            "Items": items,
            "Paging": {"IsEnd": is_end, "NextOffset": next_offset, "Totals": totals},
        },
    }


class TestZhihuCollector:
    def _collector(self, envelope, fulltext=None):
        from app.collector.adapters.zhihu import ZhihuCollector

        c = ZhihuCollector()
        c.page_delay = 0
        c._get_json = AsyncMock(return_value=envelope)
        c._fetch_fulltext = AsyncMock(return_value=fulltext)
        return c

    @pytest.mark.asyncio
    async def test_fetch_articles_with_auth_headers(self):
        """初始游标从 article 源拉取；请求带 Bearer + X-Request-Timestamp 头"""
        c = self._collector(_zh_envelope([_zh_item()]))
        articles, new_cursor = await c.fetch_since(None)
        _, kwargs = c._get_json.call_args
        assert kwargs["params"]["ContentType"] == "article"
        assert kwargs["params"]["Offset"] == 0
        assert kwargs["headers"]["Authorization"].startswith("Bearer ")
        assert kwargs["headers"]["X-Request-Timestamp"].isdigit()
        assert len(articles) == 1
        a = articles[0]
        assert a.platform == "zhihu"
        assert a.external_id == "article:123"
        assert a.title == "知乎文章"
        assert a.publish_time == datetime.fromtimestamp(1700000000)
        assert new_cursor == "answer:0"

    @pytest.mark.asyncio
    async def test_summary_fallback_when_no_fulltext(self):
        """全文抓取失败时降级为 Summary 并标记 extra.fulltext=False"""
        c = self._collector(_zh_envelope([_zh_item()]), fulltext=None)
        articles, _ = await c.fetch_since(None)
        assert articles[0].html_content == "<p>摘要</p>"
        assert articles[0].extra["fulltext"] is False

    @pytest.mark.asyncio
    async def test_fulltext_preferred(self):
        c = self._collector(_zh_envelope([_zh_item()]), fulltext="<p>全文正文</p>")
        articles, _ = await c.fetch_since(None)
        assert articles[0].html_content == "<p>全文正文</p>"
        assert articles[0].extra["fulltext"] is True

    @pytest.mark.asyncio
    async def test_answer_body_prefixed_with_question_title(self):
        c = self._collector(_zh_envelope([_zh_item(ctype="answer", id_="9", title="如何防潮")]))
        articles, _ = await c.fetch_since(None)
        assert articles[0].external_id == "answer:9"
        assert articles[0].html_content.startswith("问题：如何防潮")

    @pytest.mark.asyncio
    async def test_offset_pagination_cursor(self):
        c = self._collector(_zh_envelope([_zh_item()], is_end=False, next_offset="50", totals=100))
        _, new_cursor = await c.fetch_since(None)
        assert new_cursor == "article:50"

    @pytest.mark.asyncio
    async def test_cursor_transitions_article_to_answer_then_end(self):
        c = self._collector(_zh_envelope([_zh_item()]))
        _, cursor = await c.fetch_since("article:0")
        assert cursor == "answer:0"
        _, cursor = await c.fetch_since("answer:0")
        assert cursor is None
        _, kwargs = c._get_json.call_args
        assert kwargs["params"]["ContentType"] == "answer"

    @pytest.mark.asyncio
    async def test_original_url_strips_utm(self):
        item = _zh_item()
        item["Url"] = "https://zhuanlan.zhihu.com/p/123?utm_medium=openapi_platform&utm_source=x"
        c = self._collector(_zh_envelope([item]))
        articles, _ = await c.fetch_since(None)
        assert articles[0].original_url == "https://zhuanlan.zhihu.com/p/123"

    @pytest.mark.asyncio
    async def test_api_error_code_raises(self):
        from app.collector.adapters.zhihu import ZhihuApiError

        c = self._collector({"Code": 20001, "Message": "auth failed", "Data": None})
        with pytest.raises(ZhihuApiError):
            await c.fetch_since(None)

    @pytest.mark.asyncio
    async def test_health_check(self):
        c = self._collector(_zh_envelope([]))
        assert await c.health_check() is True
        c._get_json = AsyncMock(return_value={"Code": 20001, "Message": "auth failed"})
        assert await c.health_check() is False

    def test_parse_content_id_fallback(self):
        from app.collector.adapters.zhihu import parse_content_id

        assert parse_content_id("https://zhuanlan.zhihu.com/p/77", "article") == "article:77"
        assert parse_content_id("https://weird.example.com/abc", "article") == "https://weird.example.com/abc"[:200]


class TestBilibiliCollector:
    @pytest.mark.asyncio
    async def test_parses_articles(self):
        from app.collector.adapters.bilibili import BilibiliCollector

        c = BilibiliCollector()
        c._get_json = AsyncMock(return_value={
            "data": {"articles": [{"id": 77, "title": "B站专栏", "content": "<p>b</p>", "publish_time": 1700000000}], "total": 100}
        })
        articles, new_cursor = await c.fetch_since(None)
        assert len(articles) == 1
        assert articles[0].platform == "bilibili"
        assert articles[0].external_id == "77"
        assert articles[0].original_url == "https://www.bilibili.com/read/cv77"
        assert new_cursor == "2"


class TestOfficialWebsiteCollector:
    @pytest.mark.asyncio
    async def test_parses_articles(self, monkeypatch):
        from app.collector.adapters.official_website import OfficialWebsiteCollector
        from app.core.config import settings

        monkeypatch.setattr(settings, "official_website_base_url", "https://www.example.com")
        monkeypatch.setattr(settings, "official_website_list_path", "/api/news")
        c = OfficialWebsiteCollector()
        c._get_json = AsyncMock(return_value={
            "articles": [{"id": 1, "title": "官网公告", "url": "https://www.example.com/a/1", "html": "<p>公告</p>", "publish_time": "2026-07-31T10:00:00"}],
            "has_more": False,
        })
        articles, new_cursor = await c.fetch_since(None)
        assert c._get_json.call_args.args[0] == "https://www.example.com/api/news"
        assert len(articles) == 1
        assert articles[0].platform == "official_website"
        assert articles[0].title == "官网公告"
        assert articles[0].publish_time == datetime(2026, 7, 31, 10, 0, 0)
        assert new_cursor is None
