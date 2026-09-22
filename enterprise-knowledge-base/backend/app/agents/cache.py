"""Redis 热缓存 — FAQ 向量缓存 + 查询结果缓存"""

import json
from dataclasses import dataclass
from typing import Any

import redis.asyncio as aioredis

from app.core.config import settings
from app.core.logging import logger


@dataclass
class CacheConfig:
    host: str
    port: int
    default_ttl: int = 300


def create_cache_config() -> CacheConfig:
    return CacheConfig(
        host=settings.redis_host,
        port=settings.redis_port,
        default_ttl=300,
    )


class RedisCache:
    def __init__(self, client: aioredis.Redis | None = None):
        self._client = client

    async def _ensure_client(self) -> aioredis.Redis:
        if self._client is None:
            cfg = create_cache_config()
            self._client = aioredis.Redis(host=cfg.host, port=cfg.port, decode_responses=True)
        return self._client

    async def get(self, key: str) -> dict | None:
        try:
            client = await self._ensure_client()
            data = await client.get(key)
            if data:
                return json.loads(data) if isinstance(data, str) else data
        except Exception:
            logger.warning("redis_cache_get_error", key=key, exc_info=True)
        return None

    async def set(self, key: str, value: dict, ttl: int = 300) -> bool:
        try:
            client = await self._ensure_client()
            raw = json.dumps(value, ensure_ascii=False)
            await client.set(key, raw)
            await client.expire(key, ttl)
            return True
        except Exception:
            logger.warning("redis_cache_set_error", key=key, exc_info=True)
            return False

    async def invalidate(self, pattern: str) -> int:
        try:
            client = await self._ensure_client()
            keys = await client.keys(pattern)
            if keys:
                return await client.delete(*keys)
        except Exception:
            logger.warning("redis_cache_invalidate_error", pattern=pattern, exc_info=True)
        return 0

    async def set_json(self, key: str, data: Any, ttl: int = 300) -> bool:
        """存储 JSON 序列化数据"""
        try:
            client = await self._ensure_client()
            raw = json.dumps(data, ensure_ascii=False)
            await client.set(key, raw)
            if ttl > 0:
                await client.expire(key, ttl)
            return True
        except Exception:
            logger.warning("redis_cache_set_json_error", key=key, exc_info=True)
            return False

    async def get_json(self, key: str) -> Any | None:
        """获取 JSON 序列化数据"""
        return await self.get(key)


_cache_instance: RedisCache | None = None


def get_cache() -> RedisCache:
    global _cache_instance
    if _cache_instance is None:
        _cache_instance = RedisCache()
    return _cache_instance


def build_cache_key(query: str, scope: str, role: str) -> str:
    return f"cache:qa:{scope}:{role}:{query}"


def build_faq_cache_key(scope: str) -> str:
    return f"cache:faq:vectors:{scope}"
