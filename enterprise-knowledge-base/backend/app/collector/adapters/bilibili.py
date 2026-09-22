"""B站专栏采集器 — 创作中心专栏图文（需平台凭证）。

接口形态以 B 站创作中心为准；此处按「鉴权 + 页码分页列表」常见结构实现，
凭证到位后按实际接口校正字段映射即可。
"""

from app.collector.http_base import HttpCollector, parse_publish_time
from app.collector.models import RawArticle
from app.collector.registry import register
from app.core.config import settings

_BASE = "https://api.bilibili.com"
_LIST_PATH = "/x/article/creative/list"
_PAGE_SIZE = 20


@register
class BilibiliCollector(HttpCollector):
    platform = "bilibili"

    def __init__(self) -> None:
        super().__init__()
        self.source_name = settings.bilibili_source_name

    async def health_check(self) -> bool:
        return bool(settings.bilibili_access_token)

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {settings.bilibili_access_token}"}

    async def fetch_since(self, cursor: str | None) -> tuple[list[RawArticle], str | None]:
        page = int(cursor) if cursor else 1
        data = await self._get_json(
            f"{_BASE}{_LIST_PATH}",
            params={"mid": settings.bilibili_mid, "pn": page, "ps": _PAGE_SIZE},
            headers=self._headers(),
        )
        payload = data.get("data", {})
        items = payload.get("articles", [])
        articles = [
            RawArticle(
                platform=self.platform,
                external_id=str(item.get("id", "")),
                title=item.get("title", ""),
                html_content=item.get("content") or item.get("summary", ""),
                original_url=f"https://www.bilibili.com/read/cv{item.get('id', '')}",
                publish_time=parse_publish_time(item.get("publish_time") or item.get("ctime")),
                source_name=self.source_name,
            )
            for item in items
        ]
        total = payload.get("total", 0)
        new_cursor = str(page + 1) if page * _PAGE_SIZE < total else None
        return articles, new_cursor
