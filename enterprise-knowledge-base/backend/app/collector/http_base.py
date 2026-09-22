"""采集器 HTTP 基类 — 提供 httpx 异步客户端与 JSON/文本请求辅助。"""

from datetime import datetime

import httpx

from app.collector.base import BaseCollector
from app.core.config import settings


def parse_publish_time(value: object) -> datetime | None:
    """将时间戳（秒）或 ISO 字符串解析为 datetime，无法解析返回 None。"""
    if isinstance(value, (int, float)) and value > 0:
        return datetime.fromtimestamp(value)
    if isinstance(value, str) and value.strip():
        try:
            return datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
        except ValueError:
            return None
    return None


class HttpCollector(BaseCollector):
    """带 HTTP 客户端的采集器基类。子类实现 ``fetch_since`` 与平台鉴权。"""

    def __init__(self) -> None:
        self._client: httpx.AsyncClient | None = None

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=settings.collector_request_timeout)
        return self._client

    async def _get_json(self, url: str, *, params: dict | None = None, headers: dict | None = None) -> dict:
        resp = await self._get_client().get(url, params=params, headers=headers)
        resp.raise_for_status()
        return resp.json()

    async def _post_json(
        self,
        url: str,
        *,
        json: dict | None = None,
        params: dict | None = None,
        headers: dict | None = None,
    ) -> dict:
        resp = await self._get_client().post(url, json=json, params=params, headers=headers)
        resp.raise_for_status()
        return resp.json()

    async def _get_text(self, url: str, *, params: dict | None = None, headers: dict | None = None) -> str:
        resp = await self._get_client().get(url, params=params, headers=headers)
        resp.raise_for_status()
        return resp.text

    async def aclose(self) -> None:
        if self._client is not None and not self._client.is_closed:
            await self._client.aclose()
