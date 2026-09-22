"""企业官网采集器 — CMS 接口 / 定向栏目采集（按站点配置）。

默认按 CMS JSON 列表接口实现：GET {base_url}{list_path}?page=&size=
→ {"articles": [{id, title, url, html/content, publish_time}], "has_more": bool}。
若官网无 JSON 接口，可改造为抓取栏目列表页 + 文章页 HTML（cleaner 会提取正文）。
"""

from app.collector.http_base import HttpCollector, parse_publish_time
from app.collector.models import RawArticle
from app.collector.registry import register
from app.core.config import settings

_PAGE_SIZE = 20


@register
class OfficialWebsiteCollector(HttpCollector):
    platform = "official_website"

    def __init__(self) -> None:
        super().__init__()
        self.source_name = settings.official_website_source_name

    async def health_check(self) -> bool:
        return bool(settings.official_website_base_url)

    async def fetch_since(self, cursor: str | None) -> tuple[list[RawArticle], str | None]:
        base = settings.official_website_base_url.rstrip("/")
        path = settings.official_website_list_path or "/"
        page = int(cursor) if cursor else 1
        data = await self._get_json(f"{base}{path}", params={"page": page, "size": _PAGE_SIZE})
        items = data.get("articles", data.get("data", []))
        articles = [
            RawArticle(
                platform=self.platform,
                external_id=str(item.get("id") or item.get("url") or ""),
                title=item.get("title", ""),
                html_content=item.get("html") or item.get("content", ""),
                original_url=item.get("url", ""),
                publish_time=parse_publish_time(item.get("publish_time")),
                source_name=self.source_name,
            )
            for item in items
        ]
        new_cursor = str(page + 1) if data.get("has_more", False) else None
        return articles, new_cursor
