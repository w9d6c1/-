"""微信公众号采集器 — 三源全量采集。

数据源（互补，按序拉取）：
1. 素材库 material/batchget_material（type=news）— 永久图文素材，
   覆盖早期群发文章（可追溯至账号创建初期）。
2. 发布 freepublish/batchget — "发布"功能产出的文章（近年内容）。
3. 草稿箱 draft/batchget — 未发布的图文（含仅群发/待发布内容），
   与已发布文章重复的部分由入库三级去重自动合并。

游标格式：None → 素材库起始；"material:{offset}" → 素材库翻页；
"freepublish:{offset}" → 发布源翻页；"draft:{offset}" → 草稿箱翻页；
全部拉完返回 None。
素材/发布源 external_id 优先用文章 URL（与存量链接一致，保证跨源去重）；
草稿箱预览 URL 为临时链接，external_id 用 "draft:{media_id}:{idx}"。

接口文档：
- https://developers.weixin.qq.com/doc/offiaccount/Asset_Management/
- https://developers.weixin.qq.com/doc/offiaccount/Publish/
- https://developers.weixin.qq.com/doc/offiaccount/Draft_Box/
"""

from datetime import datetime

from app.collector.http_base import HttpCollector
from app.collector.models import RawArticle
from app.collector.registry import register
from app.core.config import settings

_TOKEN_URL = "https://api.weixin.qq.com/cgi-bin/token"
_MATERIAL_URL = "https://api.weixin.qq.com/cgi-bin/material/batchget_material"
_FREEPUBLISH_URL = "https://api.weixin.qq.com/cgi-bin/freepublish/batchget"
_DRAFT_URL = "https://api.weixin.qq.com/cgi-bin/draft/batchget"
_DRAFT_GET_URL = "https://api.weixin.qq.com/cgi-bin/draft/get"
_PAGE_SIZE = 20


@register
class WechatCollector(HttpCollector):
    platform = "wechat"

    def __init__(self) -> None:
        super().__init__()
        self.source_name = settings.wechat_mp_source_name
        self._access_token: str | None = None

    async def health_check(self) -> bool:
        try:
            await self._get_access_token()
            return True
        except Exception:
            return False

    async def _get_access_token(self) -> str:
        if self._access_token:
            return self._access_token
        data = await self._get_json(
            _TOKEN_URL,
            params={
                "grant_type": "client_credential",
                "appid": settings.wechat_mp_appid,
                "secret": settings.wechat_mp_appsecret,
            },
        )
        token = data.get("access_token")
        if not token:
            raise RuntimeError(f"wechat token error: {data.get('errmsg', data)}")
        self._access_token = token
        return token

    @staticmethod
    def _parse_cursor(cursor: str | None) -> tuple[str, int]:
        """解析游标为 (源, offset)；None/非法值回退素材库起点"""
        if cursor and ":" in cursor:
            source, _, offset_str = cursor.partition(":")
            if source in ("material", "freepublish", "draft") and offset_str.isdigit():
                return source, int(offset_str)
        return "material", 0

    @staticmethod
    def _to_time(ts: object) -> datetime | None:
        return datetime.fromtimestamp(ts) if isinstance(ts, (int, float)) and ts > 0 else None

    async def fetch_since(self, cursor: str | None) -> tuple[list[RawArticle], str | None]:
        token = await self._get_access_token()
        source, offset = self._parse_cursor(cursor)
        if source == "material":
            return await self._fetch_material_page(token, offset)
        if source == "freepublish":
            return await self._fetch_freepublish_page(token, offset)
        return await self._fetch_draft_page(token, offset)

    async def resolve_draft_url(self, media_id: str, news_idx: int) -> str | None:
        """实时解析草稿预览链接（tempkey 链接仅在获取瞬间有效，故按需调用）。

        草稿无永久 URL；返回 None 表示草稿已删除或序号越界。
        """
        token = await self._get_access_token()
        data = await self._post_json(
            _DRAFT_GET_URL,
            params={"access_token": token},
            json={"media_id": media_id},
        )
        items = data.get("news_item") or []
        if 0 <= news_idx < len(items):
            return str(items[news_idx].get("url") or "") or None
        return None

    async def _fetch_material_page(
        self, token: str, offset: int
    ) -> tuple[list[RawArticle], str | None]:
        data = await self._post_json(
            _MATERIAL_URL,
            params={"access_token": token},
            json={"type": "news", "offset": offset, "count": _PAGE_SIZE},
        )
        items = data.get("item") or []
        articles: list[RawArticle] = []
        for item in items:
            content = item.get("content") or {}
            publish_time = self._to_time(content.get("create_time")) or self._to_time(
                item.get("update_time")
            )
            media_id = item.get("media_id", "")
            for news_idx, news in enumerate(content.get("news_item") or []):
                url = str(news.get("url") or "")
                external_id = url[:200] if url else f"{media_id}:{news_idx}"
                articles.append(
                    RawArticle(
                        platform=self.platform,
                        external_id=external_id,
                        title=news.get("title", ""),
                        html_content=news.get("content", ""),
                        original_url=url,
                        publish_time=publish_time,
                        source_name=self.source_name,
                    )
                )
        total = data.get("total_count", 0)
        if offset + len(items) < total:
            return articles, f"material:{offset + _PAGE_SIZE}"
        # 素材库拉完，切换到发布源
        return articles, "freepublish:0"

    async def _fetch_freepublish_page(
        self, token: str, offset: int
    ) -> tuple[list[RawArticle], str | None]:
        data = await self._post_json(
            _FREEPUBLISH_URL,
            params={"access_token": token},
            json={"offset": offset, "count": _PAGE_SIZE, "no_content": 0},
        )
        items = data.get("item") or []
        articles: list[RawArticle] = []
        for item in items:
            # freepublish 接口实际返回 update_time，publish_time 兜底
            publish_time = self._to_time(item.get("publish_time")) or self._to_time(
                item.get("update_time")
            )
            media_id = item.get("media_id", "")
            for news_idx, news in enumerate(item.get("content", {}).get("news_item") or []):
                url = str(news.get("url") or "")
                external_id = url[:200] if url else f"{media_id}:{news_idx}"
                articles.append(
                    RawArticle(
                        platform=self.platform,
                        external_id=external_id,
                        title=news.get("title", ""),
                        html_content=news.get("content", ""),
                        original_url=url,
                        publish_time=publish_time,
                        source_name=self.source_name,
                    )
                )
        total = data.get("total_count", 0)
        if offset + len(items) < total:
            return articles, f"freepublish:{offset + _PAGE_SIZE}"
        # 发布源拉完，切换到草稿箱源
        return articles, "draft:0"

    async def _fetch_draft_page(
        self, token: str, offset: int
    ) -> tuple[list[RawArticle], str | None]:
        data = await self._post_json(
            _DRAFT_URL,
            params={"access_token": token},
            json={"offset": offset, "count": _PAGE_SIZE, "no_content": 0},
        )
        items = data.get("item") or []
        articles: list[RawArticle] = []
        for item in items:
            content = item.get("content") or {}
            publish_time = self._to_time(content.get("create_time")) or self._to_time(
                item.get("update_time")
            )
            media_id = item.get("media_id", "")
            for news_idx, news in enumerate(content.get("news_item") or []):
                # 草稿预览 URL 是临时链接（tempkey），不可作为稳定去重键
                external_id = f"draft:{media_id}:{news_idx}"
                articles.append(
                    RawArticle(
                        platform=self.platform,
                        external_id=external_id,
                        title=news.get("title", ""),
                        html_content=news.get("content", ""),
                        original_url="",
                        publish_time=publish_time,
                        source_name=self.source_name,
                    )
                )
        total = data.get("total_count", 0)
        if offset + len(items) < total:
            return articles, f"draft:{offset + _PAGE_SIZE}"
        return articles, None
