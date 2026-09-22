"""知乎企业号采集器 — 数据开放平台用户内容 API。

鉴权：``Bearer <Access Secret>`` + ``X-Request-Timestamp``（秒级时间戳）；
不传 ``X-OAuth-Token`` 时拉取调用方本账号的文章/回答。
接口仅返回 Summary 摘要；开启全文时按内容 Url 抓取公开页正文
（js-initialData / RichText 提取），失败降级为 Summary。

游标格式：None → ``article:0``；``article:{offset}`` 拉完切换 ``answer:0``；
``answer:{offset}`` 拉完返回 None。分页用 Offset/NextOffset（Limit 最大 50）。

接口文档：https://developer.zhihu.com（用户内容 API）
错误码：0 成功 / 20001 鉴权失败 / 30001 频率限制 / 30002 配额限制。
"""

import asyncio
import time
from urllib.parse import parse_qsl, urlparse, urlunparse

from app.collector import zhihu_page
from app.collector.http_base import HttpCollector, parse_publish_time
from app.collector.models import RawArticle
from app.collector.registry import register
from app.core.config import settings
from app.core.logging import logger

_BASE = "https://developer.zhihu.com/api/v1/user/contents"
_PAGE_SIZE = 50
_SOURCES = ("article", "answer")
_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)


class ZhihuApiError(RuntimeError):
    """知乎开放平台接口业务错误（Code != 0）。"""


def parse_content_id(url: str, content_type: str) -> str:
    """从内容链接解析稳定 external_id；无法解析时回退完整 URL。"""
    try:
        tail = urlparse(url).path.rstrip("/").rsplit("/", 1)[-1]
        if tail.isdigit():
            return f"{content_type}:{tail}"
    except (ValueError, AttributeError):
        pass
    return url[:200]


def _strip_utm(url: str) -> str:
    """去掉溯源 utm_* 查询参数，保留干净永久链接。"""
    try:
        parts = urlparse(url)
        query = "&".join(
            f"{k}={v}" for k, v in parse_qsl(parts.query, keep_blank_values=True)
            if not k.startswith("utm_")
        )
        return urlunparse(parts._replace(query=query))
    except (ValueError, AttributeError):
        return url


@register
class ZhihuCollector(HttpCollector):
    platform = "zhihu"

    def __init__(self) -> None:
        super().__init__()
        self.source_name = settings.zhihu_source_name
        self.page_delay = settings.zhihu_page_delay
        self._last_request_at = 0.0

    async def _throttle(self) -> None:
        """自限流：相邻请求间隔不小于 page_delay（平台秒级限频，错误码 30001）。"""
        now = time.monotonic()
        wait = self.page_delay - (now - self._last_request_at)
        if wait > 0:
            await asyncio.sleep(wait)
        self._last_request_at = time.monotonic()

    async def health_check(self) -> bool:
        try:
            await self._fetch_page("article", 0, limit=1)
            return True
        except Exception:
            return False

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {settings.zhihu_access_secret}",
            "X-Request-Timestamp": str(int(time.time())),
            "Content-Type": "application/json",
        }

    @staticmethod
    def _parse_cursor(cursor: str | None) -> tuple[str, int]:
        if cursor and ":" in cursor:
            source, _, offset_str = cursor.partition(":")
            if source in _SOURCES and offset_str.isdigit():
                return source, int(offset_str)
        return "article", 0

    async def _fetch_page(self, content_type: str, offset: int, limit: int = _PAGE_SIZE) -> dict:
        await self._throttle()
        data = await self._get_json(
            _BASE,
            params={
                "ContentType": content_type,
                "Offset": offset,
                "Limit": limit,
                "SortField": "ts",
                "SortOrder": "desc",
            },
            headers=self._headers(),
        )
        code = data.get("Code", 0)
        if code != 0:
            raise ZhihuApiError(f"zhihu api error: code={code} message={data.get('Message', '')}")
        return data.get("Data") or {}

    async def _fetch_fulltext(self, url: str) -> str | None:
        """抓取公开页正文；未开启/失败返回 None（调用方降级 Summary）。"""
        if not settings.zhihu_fetch_fulltext or not url:
            return None
        try:
            if self.page_delay > 0:
                await asyncio.sleep(self.page_delay)
            headers = {"User-Agent": _USER_AGENT}
            if settings.zhihu_cookie:
                headers["Cookie"] = settings.zhihu_cookie
            page_html = await self._get_text(url, headers=headers)
            return zhihu_page.extract_content_html(page_html)
        except Exception:
            logger.warning("zhihu_fulltext_fetch_failed", url=url)
            return None

    async def fetch_since(self, cursor: str | None) -> tuple[list[RawArticle], str | None]:
        source, offset = self._parse_cursor(cursor)
        data = await self._fetch_page(source, offset)
        articles = [await self._to_article(item) for item in data.get("Items") or []]
        paging = data.get("Paging") or {}
        if not paging.get("IsEnd", True):
            next_offset = paging.get("NextOffset") or str(offset + _PAGE_SIZE)
            return articles, f"{source}:{next_offset}"
        if source == "article":
            return articles, "answer:0"
        return articles, None

    async def _to_article(self, item: dict) -> RawArticle:
        ctype = str(item.get("ContentType") or "content").lower()
        url = str(item.get("Url") or "")
        title = str(item.get("Title") or "")
        fulltext = await self._fetch_fulltext(url)
        html_content = fulltext if fulltext else str(item.get("Summary") or "")
        if ctype == "answer" and title:
            html_content = f"问题：{title}\n{html_content}"
        return RawArticle(
            platform=self.platform,
            external_id=parse_content_id(url, ctype),
            title=title,
            html_content=html_content,
            original_url=_strip_utm(url),
            publish_time=parse_publish_time(item.get("CreatedAt")),
            source_name=self.source_name,
            extra={"fulltext": fulltext is not None},
        )
