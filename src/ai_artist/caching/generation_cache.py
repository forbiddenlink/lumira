"""Generation caching for cost optimization.

Caches:
- Creative intent decisions (LLM reasoning results)
- Curation scores (CLIP/aesthetic evaluations)
- Prompt processing results

Does NOT cache actual generated images (those are unique each time).
"""

import hashlib
import json
import os
from datetime import UTC, datetime
from typing import Any

from ..utils.logging import get_logger
from .redis_cache import RedisCache

logger = get_logger(__name__)


class GenerationCache:
    """Cache layer for generation-related operations.

    Caches expensive operations while preserving creative variety.
    Images themselves are NOT cached (they should be unique).
    """

    def __init__(
        self,
        redis_url: str | None = None,
        enabled: bool = True,
    ):
        """Initialize generation cache.

        Args:
            redis_url: Redis connection URL (default from env REDIS_URL)
            enabled: Whether caching is enabled
        """
        self.enabled = enabled

        # Parse Redis URL or use defaults
        effective_url: str = (
            redis_url or os.environ.get("REDIS_URL") or "redis://localhost:6379"
        )

        try:
            # Parse URL components
            if "://" in effective_url:
                # redis://host:port/db
                parts = effective_url.replace("redis://", "").split("/")
                host_port = parts[0].split(":")
                host = host_port[0]
                port = int(host_port[1]) if len(host_port) > 1 else 6379
                db = int(parts[1]) if len(parts) > 1 else 0
            else:
                host, port, db = "localhost", 6379, 0

            self.cache = RedisCache(host=host, port=port, db=db, enabled=enabled)
            self._connected = self.cache.enabled
        except Exception as e:
            logger.warning("generation_cache_init_failed", error=str(e))
            self.cache = RedisCache(enabled=False)
            self._connected = False

        logger.info(
            "generation_cache_initialized",
            enabled=enabled,
            connected=self._connected,
        )

    @property
    def is_connected(self) -> bool:
        """Check if cache is connected and operational."""
        return self._connected

    def _hash_key(self, *parts: Any) -> str:
        """Create a deterministic hash key from parts."""
        data = json.dumps(parts, sort_keys=True, default=str)
        return hashlib.sha256(data.encode()).hexdigest()[:16]

    # =========================================================================
    # Creative Intent Caching (LLM reasoning results)
    # =========================================================================

    async def get_creative_intent(
        self,
        mood: str,
        energy: float,
        time_of_day: str,
        recent_subjects: list[str],
    ) -> dict[str, Any] | None:
        """Get cached creative intent if context matches.

        Note: We intentionally include some context variation to allow
        for creative diversity. This cache helps when the same mood/energy
        state is queried multiple times in quick succession.

        Args:
            mood: Current mood
            energy: Energy level (rounded to 1 decimal)
            time_of_day: Time period (morning, afternoon, evening, night)
            recent_subjects: Recently used subjects (to avoid repetition)

        Returns:
            Cached intent dict or None
        """
        if not self._connected:
            return None

        # Round energy to reduce cache misses while maintaining variety
        energy_bucket = round(energy, 1)

        key = f"lumira:intent:{self._hash_key(mood, energy_bucket, time_of_day)}"

        cached = await self.cache.get(key)
        if cached:
            # Check if cached intent's subject is in recent subjects (avoid repetition)
            if cached.get("subject") in recent_subjects:
                logger.debug(
                    "intent_cache_skip_repetition",
                    subject=cached.get("subject"),
                )
                return None
            logger.info("intent_cache_hit", mood=mood)
            result: dict[str, Any] = cached
            return result
        return None

    async def set_creative_intent(
        self,
        mood: str,
        energy: float,
        time_of_day: str,
        intent: dict[str, Any],
        ttl: int = 1800,  # 30 minutes
    ) -> bool:
        """Cache a creative intent decision.

        Args:
            mood: Current mood
            energy: Energy level
            time_of_day: Time period
            intent: The creative intent dict
            ttl: Cache TTL in seconds

        Returns:
            True if cached successfully
        """
        if not self._connected:
            return False

        energy_bucket = round(energy, 1)
        key = f"lumira:intent:{self._hash_key(mood, energy_bucket, time_of_day)}"

        intent_data = {
            **intent,
            "cached_at": datetime.now(UTC).isoformat(),
        }

        success = await self.cache.set(key, intent_data, expire=ttl)
        if success:
            logger.info("intent_cached", mood=mood, ttl=ttl)
        return success

    # =========================================================================
    # Curation Score Caching (CLIP/aesthetic evaluations)
    # =========================================================================

    async def get_curation_score(
        self,
        image_hash: str,
        prompt: str,
    ) -> dict[str, float] | None:
        """Get cached curation scores for an image.

        Args:
            image_hash: Hash of the image content
            prompt: The prompt used (for CLIP score context)

        Returns:
            Dict with scores or None
        """
        if not self._connected:
            return None

        key = f"lumira:curation:{self._hash_key(image_hash, prompt)}"
        cached = await self.cache.get(key)
        if cached:
            logger.debug("curation_cache_hit", image_hash=image_hash[:8])
        return cached

    async def set_curation_score(
        self,
        image_hash: str,
        prompt: str,
        scores: dict[str, float],
        ttl: int = 7200,  # 2 hours
    ) -> bool:
        """Cache curation scores for an image.

        Args:
            image_hash: Hash of the image content
            prompt: The prompt used
            scores: Dict with aesthetic_score, clip_score, technical_score
            ttl: Cache TTL in seconds

        Returns:
            True if cached successfully
        """
        if not self._connected:
            return False

        key = f"lumira:curation:{self._hash_key(image_hash, prompt)}"
        return await self.cache.set(key, scores, expire=ttl)

    # =========================================================================
    # Prompt Processing Cache
    # =========================================================================

    async def get_processed_prompt(
        self,
        raw_prompt: str,
    ) -> dict[str, str] | None:
        """Get cached processed prompt (wildcards, emphasis applied).

        Args:
            raw_prompt: The raw prompt with wildcards/syntax

        Returns:
            Dict with processed positive and negative prompts
        """
        if not self._connected:
            return None

        key = f"lumira:prompt:{self._hash_key(raw_prompt)}"
        return await self.cache.get(key)

    async def set_processed_prompt(
        self,
        raw_prompt: str,
        processed: dict[str, str],
        ttl: int = 3600,  # 1 hour
    ) -> bool:
        """Cache processed prompt result.

        Args:
            raw_prompt: The raw prompt
            processed: Dict with 'positive' and 'negative' keys
            ttl: Cache TTL in seconds

        Returns:
            True if cached successfully
        """
        if not self._connected:
            return False

        key = f"lumira:prompt:{self._hash_key(raw_prompt)}"
        return await self.cache.set(key, processed, expire=ttl)

    # =========================================================================
    # Statistics
    # =========================================================================

    async def get_stats(self) -> dict[str, Any]:
        """Get cache statistics.

        Returns:
            Dict with cache stats
        """
        if not self._connected:
            return {"enabled": False, "connected": False}

        try:
            # Count keys by prefix
            intent_count = len(await self.cache.client.keys("lumira:intent:*"))
            curation_count = len(await self.cache.client.keys("lumira:curation:*"))
            prompt_count = len(await self.cache.client.keys("lumira:prompt:*"))

            return {
                "enabled": True,
                "connected": True,
                "intent_entries": intent_count,
                "curation_entries": curation_count,
                "prompt_entries": prompt_count,
                "total_entries": intent_count + curation_count + prompt_count,
            }
        except Exception as e:
            logger.warning("cache_stats_failed", error=str(e))
            return {"enabled": True, "connected": False, "error": str(e)}

    async def clear_all(self) -> int:
        """Clear all Lumira cache entries.

        Returns:
            Number of keys cleared
        """
        if not self._connected:
            return 0

        count = await self.cache.clear_pattern("lumira:*")
        logger.info("cache_cleared", count=count)
        return count

    async def close(self) -> None:
        """Close cache connection."""
        if self.cache:
            await self.cache.close()


# Singleton instance
_generation_cache: GenerationCache | None = None


def get_generation_cache() -> GenerationCache:
    """Get the singleton GenerationCache instance."""
    global _generation_cache
    if _generation_cache is None:
        _generation_cache = GenerationCache()
    return _generation_cache


async def shutdown_cache() -> None:
    """Shutdown the cache connection (call on app shutdown)."""
    global _generation_cache
    if _generation_cache is not None:
        await _generation_cache.close()
        _generation_cache = None
