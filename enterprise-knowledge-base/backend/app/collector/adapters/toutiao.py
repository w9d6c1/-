"""今日头条号采集器 — 创作者开放平台图文/专栏（需平台凭证）。

接口形态以头条创作者开放平台为准；此处按「Bearer 鉴权 + 分页列表」常见结构实现，
凭证到位后按实际接口校正字段映射即可。
"""

from app.collector.http_base import HttpCollector, parse_publish_time
from app.collector.models import RawArticle
from app.collector.registry import register
from app.core.config import settings

_BASE = "https://open.toutiao.com"
_LIST_PATH = "/article/list"
_PAGE_SIZE = 20


@register
class ToutiaoCollector(HttpCollector):
    platform = "toutiao"

    def __init__(self) -> None:
        super().__init__()
        self.source_name = settings.toutiao_source_name

    async def health_check(self) -> bool:
        return bool(settings.toutiao_access_token)

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {settings.toutiao_access_token}"}

    async def fetch_since(self, cursor: str | None) -> tuple[list[RawArticle], str | None]:
        page = int(cursor) if cursor else 1
        data = await self._get_json(
            f"{_BASE}{_LIST_PATH}",
            params={"page": page, "count": _PAGE_SIZE},
            headers=self._headers(),
        )
        payload = data.get("data", {})
        items = payload.get("list", [])
        articles = [
            RawArticle(
                platform=self.platform,
                external_id=str(item.get("id") or item.get("url") or ""),
                title=item.get("title", ""),
                html_content=item.get("content", ""),
                original_url=item.get("url", ""),
                publish_time=parse_publish_time(item.get("publish_time")),
                source_name=self.source_name,
            )
            for item in items
        ]
        new_cursor = str(page + 1) if payload.get("has_more") else None
        return articles, new_cursor
