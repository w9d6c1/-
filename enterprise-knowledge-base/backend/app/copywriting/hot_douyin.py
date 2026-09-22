"""抖音热搜抓取 — 短视频文案热点源

来源: 抖音热搜榜官方接口（与「热点宝」热榜同源数据）
- GET https://www.douyin.com/aweme/v1/web/hot/search/list/
- 返回 word_list：word(热点词) / hot_value(热度) / group_id(可拼视频链接)

视频链接: https://www.douyin.com/video/{group_id}
缓存: 模块级内存缓存，TTL 30 分钟；单源失败隔离。
"""

import asyncio
import time
from urllib.parse import quote

import httpx

from app.core.logging import logger

_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)
_HOT_URL = "https://www.douyin.com/aweme/v1/web/hot/search/list/"
CACHE_TTL_SECONDS = 1800
HTTP_TIMEOUT = 15.0
_MAX_ITEMS = 50

_cache: tuple[float, list[dict]] | None = None
_lock = asyncio.Lock()


async def fetch_douyin_hot(refresh: bool = False) -> list[dict]:
    """抓取抖音热搜榜，返回 [{rank, title, hot_value, url}]。失败时返回缓存或空列表。"""
    global _cache
    now = time.time()
    async with _lock:
        if not refresh and _cache and now - _cache[0] < CACHE_TTL_SECONDS:
            return _cache[1]

        try:
            async with httpx.AsyncClient(timeout=HTTP_TIMEOUT, follow_redirects=True) as client:
                resp = await client.get(
                    _HOT_URL,
                    params={
                        "device_platform": "webapp",
                        "aid": "6383",
                        "channel": "channel_pc_web",
                        "count": _MAX_ITEMS,
                    },
                    headers={
                        "User-Agent": _UA,
                        "Referer": "https://www.douyin.com/",
                    },
                )
                resp.raise_for_status()
                data = resp.json()
                items: list[dict] = []
                for it in data.get("data", {}).get("word_list", []):
                    word = (it.get("word") or "").strip()
                    if not word:
                        continue
                    # 注意：group_id 是热点话题 ID，不是视频 ID，/video/{id} 会提示"视频不存在"。
                    # 用搜索页链接（对该热点词搜索相关视频，页面始终有效）。
                    url = f"https://www.douyin.com/search/{quote(word)}"
                    cover = ""
                    cover_data = it.get("word_cover") or {}
                    cover_list = cover_data.get("url_list") or []
                    if cover_list:
                        cover = cover_list[0]
                    items.append({
                        "rank": len(items) + 1,
                        "title": word,
                        "hot_value": int(it.get("hot_value") or 0),
                        "url": url,
                        "cover": cover,
                    })
                _cache = (now, items[:_MAX_ITEMS])
                logger.info("douyin_hot_fetched", count=len(items))
                return _cache[1]
        except Exception as exc:
            logger.warning("douyin_hot_fetch_failed", error=str(exc))
            if _cache:
                return _cache[1]
            return []
