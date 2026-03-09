"""Tests for the GenerationCache."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ai_artist.caching.generation_cache import GenerationCache


class TestGenerationCache:
    """Test the GenerationCache class."""

    @pytest.fixture
    def mock_redis_cache(self):
        """Create a mock RedisCache."""
        mock = MagicMock()
        mock.enabled = True
        mock.get = AsyncMock(return_value=None)
        mock.set = AsyncMock(return_value=True)
        mock.close = AsyncMock()
        mock.clear_pattern = AsyncMock(return_value=5)
        mock.client = MagicMock()
        mock.client.keys = AsyncMock(return_value=[])
        return mock

    @pytest.fixture
    def cache(self, mock_redis_cache):
        """Create a GenerationCache with mocked Redis."""
        with patch(
            "ai_artist.caching.generation_cache.RedisCache",
            return_value=mock_redis_cache,
        ):
            cache = GenerationCache(enabled=True)
            cache._connected = True
            cache.cache = mock_redis_cache
            return cache

    def test_initialization(self, cache):
        """Test cache initializes successfully."""
        assert cache is not None
        assert cache.enabled is True
        assert cache.is_connected is True

    def test_initialization_disabled(self):
        """Test cache can be disabled."""
        cache = GenerationCache(enabled=False)
        assert cache.enabled is False

    def test_hash_key_deterministic(self, cache):
        """Test that hash keys are deterministic."""
        key1 = cache._hash_key("mood", 0.5, "morning")
        key2 = cache._hash_key("mood", 0.5, "morning")
        assert key1 == key2

    def test_hash_key_different_inputs(self, cache):
        """Test that different inputs produce different hashes."""
        key1 = cache._hash_key("mood1", 0.5, "morning")
        key2 = cache._hash_key("mood2", 0.5, "morning")
        assert key1 != key2

    @pytest.mark.asyncio
    async def test_get_creative_intent_cache_miss(self, cache, mock_redis_cache):
        """Test cache miss returns None."""
        mock_redis_cache.get = AsyncMock(return_value=None)

        result = await cache.get_creative_intent(
            mood="contemplative",
            energy=0.7,
            time_of_day="morning",
            recent_subjects=[],
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_get_creative_intent_cache_hit(self, cache, mock_redis_cache):
        """Test cache hit returns cached data."""
        cached_intent = {
            "subject": "sunset",
            "style": "impressionist",
            "reasoning": "The warm colors resonate with my contemplative mood",
        }
        mock_redis_cache.get = AsyncMock(return_value=cached_intent)

        result = await cache.get_creative_intent(
            mood="contemplative",
            energy=0.7,
            time_of_day="morning",
            recent_subjects=[],
        )
        assert result == cached_intent

    @pytest.mark.asyncio
    async def test_get_creative_intent_skips_recent_subject(
        self, cache, mock_redis_cache
    ):
        """Test that cache skips if subject is in recent subjects."""
        cached_intent = {
            "subject": "sunset",
            "style": "impressionist",
        }
        mock_redis_cache.get = AsyncMock(return_value=cached_intent)

        result = await cache.get_creative_intent(
            mood="contemplative",
            energy=0.7,
            time_of_day="morning",
            recent_subjects=["sunset"],  # Cached subject is recent
        )
        assert result is None  # Should skip to avoid repetition

    @pytest.mark.asyncio
    async def test_set_creative_intent(self, cache, mock_redis_cache):
        """Test caching a creative intent."""
        intent = {
            "subject": "ocean waves",
            "style": "abstract",
            "reasoning": "The rhythm of waves matches my current flow",
        }

        result = await cache.set_creative_intent(
            mood="serene",
            energy=0.6,
            time_of_day="evening",
            intent=intent,
            ttl=1800,
        )
        assert result is True
        mock_redis_cache.set.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_curation_score_cache_miss(self, cache, mock_redis_cache):
        """Test curation score cache miss."""
        mock_redis_cache.get = AsyncMock(return_value=None)

        result = await cache.get_curation_score(
            image_hash="abc123",
            prompt="beautiful sunset",
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_get_curation_score_cache_hit(self, cache, mock_redis_cache):
        """Test curation score cache hit."""
        scores = {
            "aesthetic_score": 0.85,
            "clip_score": 0.78,
            "technical_score": 0.90,
        }
        mock_redis_cache.get = AsyncMock(return_value=scores)

        result = await cache.get_curation_score(
            image_hash="abc123",
            prompt="beautiful sunset",
        )
        assert result == scores

    @pytest.mark.asyncio
    async def test_set_curation_score(self, cache, mock_redis_cache):
        """Test caching curation scores."""
        scores = {
            "aesthetic_score": 0.85,
            "clip_score": 0.78,
            "technical_score": 0.90,
        }

        result = await cache.set_curation_score(
            image_hash="abc123",
            prompt="beautiful sunset",
            scores=scores,
            ttl=7200,
        )
        assert result is True

    @pytest.mark.asyncio
    async def test_get_processed_prompt(self, cache, mock_redis_cache):
        """Test getting cached processed prompt."""
        processed = {
            "positive": "a beautiful sunset over the ocean, golden hour",
            "negative": "blurry, low quality",
        }
        mock_redis_cache.get = AsyncMock(return_value=processed)

        result = await cache.get_processed_prompt("sunset {time}")
        assert result == processed

    @pytest.mark.asyncio
    async def test_set_processed_prompt(self, cache, mock_redis_cache):
        """Test caching processed prompt."""
        processed = {
            "positive": "a beautiful sunset over the ocean",
            "negative": "blurry, low quality",
        }

        result = await cache.set_processed_prompt(
            raw_prompt="sunset {time}",
            processed=processed,
            ttl=3600,
        )
        assert result is True

    @pytest.mark.asyncio
    async def test_get_stats(self, cache, mock_redis_cache):
        """Test getting cache statistics."""
        mock_redis_cache.client.keys = AsyncMock(
            side_effect=[
                ["key1", "key2"],  # intent keys
                ["key3"],  # curation keys
                [],  # prompt keys
            ]
        )

        stats = await cache.get_stats()
        assert stats["enabled"] is True
        assert stats["connected"] is True
        assert stats["intent_entries"] == 2
        assert stats["curation_entries"] == 1
        assert stats["prompt_entries"] == 0
        assert stats["total_entries"] == 3

    @pytest.mark.asyncio
    async def test_clear_all(self, cache, mock_redis_cache):
        """Test clearing all cache entries."""
        mock_redis_cache.clear_pattern = AsyncMock(return_value=10)

        count = await cache.clear_all()
        assert count == 10
        mock_redis_cache.clear_pattern.assert_called_once_with("lumira:*")

    @pytest.mark.asyncio
    async def test_close(self, cache, mock_redis_cache):
        """Test closing cache connection."""
        await cache.close()
        mock_redis_cache.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_disconnected_cache_returns_none(self):
        """Test that disconnected cache operations return None/False."""
        cache = GenerationCache(enabled=False)
        cache._connected = False

        assert await cache.get_creative_intent("mood", 0.5, "morning", []) is None
        assert await cache.set_creative_intent("mood", 0.5, "morning", {}) is False
        assert await cache.get_curation_score("hash", "prompt") is None
        assert await cache.set_curation_score("hash", "prompt", {}) is False

    def test_energy_bucketing(self, cache):
        """Test that energy values are bucketed properly."""
        # Same bucket (0.7 rounds to 0.7)
        key1 = cache._hash_key("mood", round(0.71, 1), "morning")
        key2 = cache._hash_key("mood", round(0.74, 1), "morning")
        assert key1 == key2  # Both round to 0.7

        # Different buckets
        key3 = cache._hash_key("mood", round(0.75, 1), "morning")
        assert key1 != key3  # 0.75 rounds to 0.8
