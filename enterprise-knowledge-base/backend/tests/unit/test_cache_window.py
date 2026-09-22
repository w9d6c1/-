"""Redis 热缓存 + Token 窗口 测试 (TDD: RED)"""

import pytest


class TestRedisCache:
    def test_cache_config(self):
        from app.agents.cache import CacheConfig, create_cache_config

        cfg = create_cache_config()
        assert cfg.host == "redis"
        assert cfg.port == 6379
        assert cfg.default_ttl == 300

    @pytest.mark.asyncio
    async def test_cache_set_get(self):
        from unittest.mock import AsyncMock
        from app.agents.cache import RedisCache

        mock_redis = AsyncMock()
        mock_redis.get.return_value = '{"key": "value"}'
        mock_redis.set.return_value = True
        mock_redis.expire.return_value = True

        cache = RedisCache(client=mock_redis)
        await cache.set("test_key", {"key": "value"}, ttl=60)
        result = await cache.get("test_key")
        assert result == {"key": "value"}

    @pytest.mark.asyncio
    async def test_cache_miss(self):
        from unittest.mock import AsyncMock
        from app.agents.cache import RedisCache

        mock_redis = AsyncMock()
        mock_redis.get.return_value = None

        cache = RedisCache(client=mock_redis)
        result = await cache.get("nonexistent")
        assert result is None

    @pytest.mark.asyncio
    async def test_cache_invalidate(self):
        from unittest.mock import AsyncMock
        from app.agents.cache import RedisCache

        mock_redis = AsyncMock()
        mock_redis.keys.return_value = ["cache:qa:key1", "cache:qa:key2"]
        mock_redis.delete.return_value = 2

        cache = RedisCache(client=mock_redis)
        count = await cache.invalidate("cache:qa:*")
        assert count == 2

    def test_build_cache_key(self):
        from app.agents.cache import build_cache_key

        key = build_cache_key("考勤", scope="public", role="readonly")
        assert "考勤" in key
        assert "public" in key

    def test_faq_vector_cache_key(self):
        from app.agents.cache import build_faq_cache_key

        key = build_faq_cache_key("public")
        assert "faq" in key
        assert "public" in key


class TestTokenWindow:
    def test_token_window_trim_noop(self):
        from langchain_core.messages import HumanMessage, AIMessage
        from app.agents.window import trim_history

        msgs = [HumanMessage(content="你好"), AIMessage(content="你好！")]
        result = trim_history(msgs, max_tokens=10000)
        assert len(result) == 2

    def test_token_window_trim_oldest(self):
        from langchain_core.messages import HumanMessage
        from app.agents.window import trim_history

        msgs = [HumanMessage(content="这是一个很长的消息内容" * 200)]
        result = trim_history(msgs, max_tokens=10)
        assert len(result) == 1  # 最后一条始终保留（当前问题不能丢）

    def test_token_window_keeps_recent(self):
        from langchain_core.messages import HumanMessage, AIMessage
        from app.agents.window import trim_history

        msgs = [
            HumanMessage(content="旧消息其一"),
            AIMessage(content="旧回复其一"),
            HumanMessage(content="最新问题"),
        ]
        result = trim_history(msgs, max_tokens=10)
        assert len(result) <= 3

    def test_count_message_tokens(self):
        from langchain_core.messages import HumanMessage
        from app.agents.window import count_message_tokens

        msg = HumanMessage(content="测试消息")
        n = count_message_tokens(msg)
        assert n > 0
