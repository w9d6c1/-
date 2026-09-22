"""采集层数据模型与平台常量。

平台来源类型与 knowledge_doc.source_type 严格对齐，入库时作为 source_type 写入。
"""

from dataclasses import dataclass, field
from datetime import datetime

PLATFORM_WECHAT = "wechat"
PLATFORM_TOUTIAO = "toutiao"
PLATFORM_OFFICIAL_WEBSITE = "official_website"
PLATFORM_ZHIHU = "zhihu"
PLATFORM_BILIBILI = "bilibili"

ALL_PLATFORMS: list[str] = [
    PLATFORM_WECHAT,
    PLATFORM_TOUTIAO,
    PLATFORM_OFFICIAL_WEBSITE,
    PLATFORM_ZHIHU,
    PLATFORM_BILIBILI,
]

PLATFORM_DISPLAY_NAMES: dict[str, str] = {
    PLATFORM_WECHAT: "微信公众号",
    PLATFORM_TOUTIAO: "今日头条号",
    PLATFORM_OFFICIAL_WEBSITE: "企业官网",
    PLATFORM_ZHIHU: "知乎企业号",
    PLATFORM_BILIBILI: "B站专栏",
}


def is_valid_platform(platform: str) -> bool:
    return platform in ALL_PLATFORMS


@dataclass
class RawArticle:
    """采集器输出的标准化原始文章（清洗前）。"""

    platform: str
    external_id: str
    title: str
    html_content: str
    original_url: str
    publish_time: datetime | None = None
    source_name: str = ""
    author: str = ""
    extra: dict = field(default_factory=dict)


@dataclass
class PlatformSyncResult:
    """单平台一次同步的统计结果。"""

    platform: str
    fetched: int = 0
    ingested: int = 0
    duplicated: int = 0
    skipped: int = 0
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.error is None


@dataclass
class SyncSummary:
    """全平台一次同步的汇总结果。"""

    results: list[PlatformSyncResult] = field(default_factory=list)

    @property
    def total_fetched(self) -> int:
        return sum(r.fetched for r in self.results)

    @property
    def total_ingested(self) -> int:
        return sum(r.ingested for r in self.results)

    @property
    def failed_platforms(self) -> list[str]:
        return [r.platform for r in self.results if not r.ok]

    @property
    def all_ok(self) -> bool:
        return all(r.ok for r in self.results)
