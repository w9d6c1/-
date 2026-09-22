"""平台采集适配器 — 导入即触发各适配器的 @register 自注册。"""

from app.collector.adapters import (  # noqa: F401
    bilibili,
    official_website,
    toutiao,
    wechat,
    zhihu,
)

__all__ = ["wechat", "toutiao", "official_website", "zhihu", "bilibili"]
