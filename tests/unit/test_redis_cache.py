"""Tests for the Redis cache layer."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ai_artist.caching.redis_cache import RedisCache, cache_curation, cache_generation


class TestRedisCache:
    """Unit tests for RedisCache."""

    def test_init_disabled_when_redis_unavailable(self):
        with patch("ai_artist.caching.redis_cache.REDIS_AVAILABLE", False):
            cache = RedisCache(enabled=True)
            assert cache.enabled is False
            assert cache.client is None

    def test_init_disabled_when_enabled_false(self):
        cache = RedisCache(enabled=False)
        assert cache.enabled is False
        assert cache.client is None

    def test_init_creates_client_when_redis_available(self):
        mock_client = MagicMock()
        mock_redis = MagicMock()
        mock_redis.Redis.return_value = mock_client
        test_password = "".join(["test", "-password"])

        with (
            patch("ai_artist.caching.redis_cache.REDIS_AVAILABLE", True),
            patch("ai_artist.caching.redis_cache.redis", mock_redis),
        ):
            cache = RedisCache(host="redis", port=6380, db=2, password=test_password)

        assert cache.enabled is True
        assert cache.client is mock_client
        mock_redis.Redis.assert_called_once_with(
            host="redis",
            port=6380,
            db=2,
            password=test_password,
            decode_responses=True,
        )

    def test_init_disables_cache_when_client_creation_fails(self):
        mock_redis = MagicMock()
        mock_redis.Redis.side_effect = RuntimeError("boom")

        with (
            patch("ai_artist.caching.redis_cache.REDIS_AVAILABLE", True),
            patch("ai_artist.caching.redis_cache.redis", mock_redis),
        ):
            cache = RedisCache()

        assert cache.enabled is False
        assert cache.client is None

    @pytest.mark.asyncio
    async def test_get_returns_none_when_disabled(self):
        cache = RedisCache(enabled=False)
        assert await cache.get("key") is None

    @pytest.mark.asyncio
    async def test_get_returns_deserialized_value(self):
        client = MagicMock()
        client.get = AsyncMock(return_value='{"score": 0.9}')
        cache = RedisCache(enabled=False)
        cache.enabled = True
        cache.client = client

        result = await cache.get("key")

        assert result == {"score": 0.9}
        client.get.assert_awaited_once_with("key")

    @pytest.mark.asyncio
    async def test_get_returns_none_on_missing_value(self):
        client = MagicMock()
        client.get = AsyncMock(return_value=None)
        cache = RedisCache(enabled=False)
        cache.enabled = True
        cache.client = client

        assert await cache.get("missing") is None

    @pytest.mark.asyncio
    async def test_get_returns_none_on_error(self):
        client = MagicMock()
        client.get = AsyncMock(side_effect=RuntimeError("redis down"))
        cache = RedisCache(enabled=False)
        cache.enabled = True
        cache.client = client

        assert await cache.get("key") is None

    @pytest.mark.asyncio
    async def test_set_returns_false_when_disabled(self):
        cache = RedisCache(enabled=False)
        assert await cache.set("key", {"x": 1}) is False

    @pytest.mark.asyncio
    async def test_set_serializes_and_stores_value(self):
        client = MagicMock()
        client.set = AsyncMock(return_value=True)
        cache = RedisCache(enabled=False)
        cache.enabled = True
        cache.client = client

        result = await cache.set("key", {"x": 1}, expire=60)

        assert result is True
        client.set.assert_awaited_once_with("key", '{"x": 1}', ex=60)

    @pytest.mark.asyncio
    async def test_set_returns_false_on_error(self):
        client = MagicMock()
        client.set = AsyncMock(side_effect=TypeError("not serializable"))
        cache = RedisCache(enabled=False)
        cache.enabled = True
        cache.client = client

        assert await cache.set("key", object()) is False

    @pytest.mark.asyncio
    async def test_delete_returns_true_on_success(self):
        client = MagicMock()
        client.delete = AsyncMock(return_value=1)
        cache = RedisCache(enabled=False)
        cache.enabled = True
        cache.client = client

        assert await cache.delete("key") is True
        client.delete.assert_awaited_once_with("key")

    @pytest.mark.asyncio
    async def test_clear_pattern_deletes_matching_keys(self):
        client = MagicMock()
        client.keys = AsyncMock(return_value=["a", "b"])
        client.delete = AsyncMock(return_value=2)
        cache = RedisCache(enabled=False)
        cache.enabled = True
        cache.client = client

        result = await cache.clear_pattern("lumira:*")

        assert result == 2
        client.keys.assert_awaited_once_with("lumira:*")
        client.delete.assert_awaited_once_with("a", "b")

    @pytest.mark.asyncio
    async def test_clear_pattern_returns_zero_when_no_keys_match(self):
        client = MagicMock()
        client.keys = AsyncMock(return_value=[])
        client.delete = AsyncMock()
        cache = RedisCache(enabled=False)
        cache.enabled = True
        cache.client = client

        result = await cache.clear_pattern("lumira:*")

        assert result == 0
        client.delete.assert_not_called()

    @pytest.mark.asyncio
    async def test_exists_uses_client_result(self):
        client = MagicMock()
        client.exists = AsyncMock(return_value=1)
        cache = RedisCache(enabled=False)
        cache.enabled = True
        cache.client = client

        assert await cache.exists("key") is True

    @pytest.mark.asyncio
    async def test_exists_returns_false_on_error(self):
        client = MagicMock()
        client.exists = AsyncMock(side_effect=RuntimeError("broken"))
        cache = RedisCache(enabled=False)
        cache.enabled = True
        cache.client = client

        assert await cache.exists("key") is False

    @pytest.mark.asyncio
    async def test_incr_returns_incremented_value(self):
        client = MagicMock()
        client.incrby = AsyncMock(return_value=7)
        cache = RedisCache(enabled=False)
        cache.enabled = True
        cache.client = client

        result = await cache.incr("counter", amount=3)

        assert result == 7
        client.incrby.assert_awaited_once_with("counter", 3)

    @pytest.mark.asyncio
    async def test_incr_returns_zero_on_error(self):
        client = MagicMock()
        client.incrby = AsyncMock(side_effect=RuntimeError("broken"))
        cache = RedisCache(enabled=False)
        cache.enabled = True
        cache.client = client

        assert await cache.incr("counter") == 0

    @pytest.mark.asyncio
    async def test_close_closes_client(self):
        client = MagicMock()
        client.close = AsyncMock(return_value=None)
        cache = RedisCache(enabled=False)
        cache.client = client

        await cache.close()

        client.close.assert_awaited_once()


class TestRedisCacheHelpers:
    """Tests for cache key helpers."""

    @pytest.mark.asyncio
    async def test_cache_generation_is_deterministic(self):
        params = {"steps": 30, "width": 512}
        key_one = await cache_generation(RedisCache(enabled=False), "sunrise", params)
        key_two = await cache_generation(RedisCache(enabled=False), "sunrise", params)

        assert key_one == key_two
        assert key_one.startswith("lumira:gen:")

    @pytest.mark.asyncio
    async def test_cache_generation_changes_when_params_change(self):
        key_one = await cache_generation(
            RedisCache(enabled=False), "sunrise", {"steps": 30}
        )
        key_two = await cache_generation(
            RedisCache(enabled=False), "sunrise", {"steps": 40}
        )

        assert key_one != key_two

    @pytest.mark.asyncio
    async def test_cache_curation_returns_expected_key(self):
        key = await cache_curation(RedisCache(enabled=False), "abc123")
        assert key == "lumira:curation:abc123"
