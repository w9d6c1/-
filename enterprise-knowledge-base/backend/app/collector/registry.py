"""采集器注册表 — 平台 → 采集器实例。适配器以 @register 装饰器自注册。"""

from app.collector.base import BaseCollector
from app.core.logging import logger

_REGISTRY: dict[str, type[BaseCollector]] = {}
_adapters_loaded = False


def register(collector_cls: type[BaseCollector]) -> type[BaseCollector]:
    """类装饰器：把采集器按 platform 注册。"""
    if not collector_cls.platform:
        raise ValueError(f"{collector_cls.__name__} 未设置 platform")
    _REGISTRY[collector_cls.platform] = collector_cls
    return collector_cls


def _ensure_adapters_loaded() -> None:
    """惰性导入 adapters 包触发各适配器自注册（仅一次）。"""
    global _adapters_loaded
    if _adapters_loaded:
        return
    _adapters_loaded = True
    try:
        from app.collector import adapters  # noqa: F401
    except Exception:
        logger.warning("collector_adapters_load_failed", exc_info=True)


def get_collector(platform: str) -> BaseCollector:
    _ensure_adapters_loaded()
    cls = _REGISTRY.get(platform)
    if cls is None:
        raise KeyError(f"未注册的采集平台: {platform}")
    return cls()


def available_platforms() -> list[str]:
    _ensure_adapters_loaded()
    return list(_REGISTRY.keys())


def available_collectors() -> dict[str, BaseCollector]:
    _ensure_adapters_loaded()
    return {platform: cls() for platform, cls in _REGISTRY.items()}
