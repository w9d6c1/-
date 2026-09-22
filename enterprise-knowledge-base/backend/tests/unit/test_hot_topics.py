"""单元测试 — 今日热点抓取与智能选题推荐"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.articles import hot_topics
from app.articles.hot_topics import (
    _fetch_baidu,
    _fetch_toutiao,
    _fetch_weibo,
    _fetch_zhihu,
    get_hot_topics,
    recommend_titles,
)


def _fake_client(payload: dict, status_code: int = 200):
    """构造返回固定 JSON 的 mock httpx client"""
    resp = MagicMock()
    resp.status_code = status_code
    resp.raise_for_status = MagicMock()
    resp.json = MagicMock(return_value=payload)
    client = MagicMock()
    client.get = AsyncMock(return_value=resp)
    return client


class TestFetchers:
    @pytest.mark.asyncio
    async def test_parse_baidu(self):
        payload = {
            "data": {
                "cards": [{
                    "content": [{
                        "content": [
                            {"word": "热点一", "hotScore": "1000", "url": "https://a"},
                            {"word": "热点二", "hotScore": "900", "url": "https://b"},
                        ]
                    }]
                }]
            }
        }
        items = await _fetch_baidu(_fake_client(payload))
        assert len(items) == 2
        assert items[0]["title"] == "热点一"
        assert items[0]["hot_value"] == 1000
        assert items[1]["rank"] == 2

    @pytest.mark.asyncio
    async def test_parse_weibo_skips_ads(self):
        payload = {
            "data": {
                "realtime": [
                    {"word": "正常热搜", "num": 5000},
                    {"word": "广告位", "num": 100, "is_ad": 1},
                ]
            }
        }
        items = await _fetch_weibo(_fake_client(payload))
        assert len(items) == 1
        assert items[0]["title"] == "正常热搜"
        assert "weibo.com" in items[0]["url"]

    @pytest.mark.asyncio
    async def test_parse_zhihu(self):
        payload = {
            "data": [
                {
                    "target": {"title": "知乎问题一", "url": "https://zhihu.com/q/1"},
                    "detail_text": "1234 万热度",
                },
                {"target": {"title": ""}, "detail_text": ""},
            ]
        }
        items = await _fetch_zhihu(_fake_client(payload))
        assert len(items) == 1
        assert items[0]["title"] == "知乎问题一"
        assert items[0]["hot_value"] == 1234

    @pytest.mark.asyncio
    async def test_parse_toutiao(self):
        payload = {
            "data": [
                {"Title": "头条热点", "HotValue": 8888, "Url": "https://tt"},
                {"Title": "", "HotValue": 0},
            ]
        }
        items = await _fetch_toutiao(_fake_client(payload))
        assert len(items) == 1
        assert items[0]["title"] == "头条热点"
        assert items[0]["hot_value"] == 8888


class TestCache:
    @pytest.fixture(autouse=True)
    def _clear_cache(self):
        hot_topics._cache.clear()
        yield
        hot_topics._cache.clear()

    @pytest.mark.asyncio
    async def test_cache_hit_no_refetch(self):
        """30 分钟内二次请求命中缓存，不重复抓取"""
        with patch(
            "app.articles.hot_topics._fetch_source",
            new_callable=AsyncMock,
            return_value=[{"rank": 1, "title": "t", "hot_value": 1, "url": ""}],
        ) as mock_fetch:
            first = await get_hot_topics()
            second = await get_hot_topics()
            assert mock_fetch.call_count == 4  # 仅首轮 4 源各抓一次
            assert first["sources"]["baidu"]["ok"] is True
            assert second["sources"]["toutiao"]["items"][0]["title"] == "t"

    @pytest.mark.asyncio
    async def test_refresh_bypasses_cache(self):
        with patch(
            "app.articles.hot_topics._fetch_source",
            new_callable=AsyncMock,
            return_value=[{"rank": 1, "title": "t", "hot_value": 1, "url": ""}],
        ) as mock_fetch:
            await get_hot_topics()
            await get_hot_topics(refresh=True)
            assert mock_fetch.call_count == 8

    @pytest.mark.asyncio
    async def test_failed_source_marked_unavailable(self):
        async def fake_fetch(source: str):
            if source == "weibo":
                return []
            return [{"rank": 1, "title": source, "hot_value": 1, "url": ""}]

        with patch("app.articles.hot_topics._fetch_source", side_effect=fake_fetch):
            result = await get_hot_topics()
            assert result["sources"]["weibo"]["ok"] is False
            assert result["sources"]["baidu"]["ok"] is True

    @pytest.mark.asyncio
    async def test_failed_source_falls_back_to_stale_cache(self):
        """刷新失败时回退旧缓存并标记 stale"""
        stale_item = {"rank": 1, "title": "旧数据", "hot_value": 1, "url": ""}
        hot_topics._cache["baidu"] = (0.0, [stale_item])

        async def fake_fetch(source: str):
            return []

        with patch("app.articles.hot_topics._fetch_source", side_effect=fake_fetch):
            result = await get_hot_topics(refresh=True)
            assert result["sources"]["baidu"]["ok"] is True
            assert result["sources"]["baidu"]["stale"] is True
            assert result["sources"]["baidu"]["items"][0]["title"] == "旧数据"


def _fake_hot_data(baidu_titles: list[str] | None = None) -> dict:
    """构造 get_hot_topics 的返回结构；baidu_titles 非空时百度源可用"""
    sources = {}
    for s in ("baidu", "weibo", "zhihu", "toutiao"):
        if s == "baidu" and baidu_titles:
            items = [
                {"rank": i + 1, "title": t, "hot_value": 1, "url": ""}
                for i, t in enumerate(baidu_titles)
            ]
            sources[s] = {"ok": True, "items": items, "cached_at": 1}
        else:
            sources[s] = {"ok": False, "items": [], "cached_at": None}
    return {"sources": sources, "updated_at": 1}


class TestRecommend:
    @pytest.mark.asyncio
    async def test_recommend_parses_llm_json(self, db_session):
        fake_llm_response = '''```json
[
  {
    "hot_title": "南方持续强降雨",
    "source": "baidu",
    "reason": "暴雨导致地下室渗水话题热度高，可结合电渗透防潮技术",
    "suggested_topic": "暴雨季节地下室防潮：电渗透技术如何解决渗水难题",
    "titles": ["暴雨过后，你家地下室还好吗？", "地下室防潮黑科技实测"]
  }
]
```'''
        fake_hot = _fake_hot_data(["南方持续强降雨"])
        with (
            patch(
                "app.articles.hot_topics.get_hot_topics",
                new_callable=AsyncMock, return_value=fake_hot,
            ),
            patch(
                "app.articles.hot_topics.call_llm_with_retry",
                new_callable=AsyncMock, return_value=fake_llm_response,
            ),
        ):
            result = await recommend_titles(db_session)
            assert result["hot_count"] == 1
            assert len(result["recommendations"]) == 1
            rec = result["recommendations"][0]
            assert rec["hot_title"] == "南方持续强降雨"
            assert len(rec["titles"]) == 2
            assert rec["suggested_topic"]

    @pytest.mark.asyncio
    async def test_recommend_no_hot_data(self, db_session):
        fake_hot = _fake_hot_data(None)
        with patch(
            "app.articles.hot_topics.get_hot_topics",
            new_callable=AsyncMock, return_value=fake_hot,
        ):
            result = await recommend_titles(db_session)
            assert result["recommendations"] == []
            assert result["hot_count"] == 0
            assert result["message"]

    @pytest.mark.asyncio
    async def test_recommend_llm_failure_returns_message(self, db_session):
        fake_hot = _fake_hot_data(["热点"])
        with (
            patch(
                "app.articles.hot_topics.get_hot_topics",
                new_callable=AsyncMock, return_value=fake_hot,
            ),
            patch(
                "app.articles.hot_topics.call_llm_with_retry",
                side_effect=RuntimeError("LLM down"),
            ),
        ):
            result = await recommend_titles(db_session)
            assert result["recommendations"] == []
            assert "失败" in result["message"]

    @pytest.mark.asyncio
    async def test_company_direction_injected_into_prompt(self, db_session):
        """公司方向应进入 LLM prompt，且优先指导选题"""
        fake_hot = _fake_hot_data(["热点"])
        fake_llm_response = "[]"
        captured: dict = {}

        async def fake_call(llm, messages, **kwargs):
            captured["prompt"] = messages[0]["content"]
            return fake_llm_response

        with (
            patch(
                "app.articles.hot_topics.get_hot_topics",
                new_callable=AsyncMock, return_value=fake_hot,
            ),
            patch(
                "app.articles.hot_topics.call_llm_with_retry",
                new=fake_call,
            ),
        ):
            await recommend_titles(db_session, company_direction="招商加盟、产品优势")
            assert "招商加盟、产品优势" in captured["prompt"]
            assert "公司本次创作的指定方向" in captured["prompt"]

    @pytest.mark.asyncio
    async def test_empty_company_direction_omits_section(self, db_session):
        """方向为空时不注入方向约束，保持原有行为"""
        fake_hot = _fake_hot_data(["热点"])
        captured: dict = {}

        async def fake_call(llm, messages, **kwargs):
            captured["prompt"] = messages[0]["content"]
            return "[]"

        with (
            patch(
                "app.articles.hot_topics.get_hot_topics",
                new_callable=AsyncMock, return_value=fake_hot,
            ),
            patch(
                "app.articles.hot_topics.call_llm_with_retry",
                new=fake_call,
            ),
        ):
            await recommend_titles(db_session)
            assert "公司本次创作的指定方向" not in captured["prompt"]
