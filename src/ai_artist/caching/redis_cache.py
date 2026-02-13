"""Redis caching layer for AI Artist."""

import json
from typing import Any

try:
    import redis.asyncio as redis  # type: ignore[import-untyped]

    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False
    redis = None  # type: ignore[assignment]

from ..utils.logging import get_logger

logger = get_logger(__name__)


class RedisCache:
    """Async Redis cache wrapper with graceful fallback."""

    def __init__(
        self,
        host: str = "localhost",
        port: int = 6379,
        db: int = 0,
        password: str | None = None,
        enabled: bool = True,
    ) -> None:
        """Initialize Redis cache.

        Args:
            host: Redis host address
            port: Redis port number
            db: Redis database number
            password: Optional Redis password
            enabled: Whether caching is enabled
        """
        self.enabled = enabled and REDIS_AVAILABLE
        self.client: Any = None

        if not REDIS_AVAILABLE and enabled:
            logger.warning(
                "redis_not_available",
                message="redis package not installed, caching disabled",
            )

        if self.enabled:
            try:
                self.client = redis.Redis(
                    host=host,
                    port=port,
                    db=db,
                    password=password,
                    decode_responses=True,
                )
                logger.info(
                    "redis_initialized",
                    host=host,
                    port=port,
                    db=db,
                )
            except Exception as e:
                logger.error("redis_init_error", error=str(e))
                self.enabled = False

    async def get(self, key: str) -> Any | None:
        """Get value from cache.

        Args:
            key: Cache key

        Returns:
            Cached value or None if not found
        """
        if not self.enabled or not self.client:
            return None

        try:
            value = await self.client.get(key)
            if value:
                return json.loads(value)
            return None
        except Exception as e:
            logger.warning("redis_get_error", key=key, error=str(e))
            return None

    async def set(
        self,
        key: str,
        value: Any,
        expire: int | None = None,
    ) -> bool:
        """Set value in cache.

        Args:
            key: Cache key
            value: Value to cache (must be JSON-serializable)
            expire: Optional TTL in seconds

        Returns:
            True if successful, False otherwise
        """
        if not self.enabled or not self.client:
            return False

        try:
            serialized = json.dumps(value)
            await self.client.set(key, serialized, ex=expire)
            return True
        except Exception as e:
            logger.warning("redis_set_error", key=key, error=str(e))
            return False

    async def delete(self, key: str) -> bool:
        """Delete key from cache.

        Args:
            key: Cache key

        Returns:
            True if deleted, False otherwise
        """
        if not self.enabled or not self.client:
            return False

        try:
            await self.client.delete(key)
            return True
        except Exception as e:
            logger.warning("redis_delete_error", key=key, error=str(e))
            return False

    async def clear_pattern(self, pattern: str) -> int:
        """Delete all keys matching pattern.

        Args:
            pattern: Redis key pattern (e.g., "aria:*")

        Returns:
            Number of keys deleted
        """
        if not self.enabled or not self.client:
            return 0

        try:
            keys = await self.client.keys(pattern)
            if keys:
                deleted = await self.client.delete(*keys)
                return int(deleted)
            return 0
        except Exception as e:
            logger.warning("redis_clear_error", pattern=pattern, error=str(e))
            return 0

    async def exists(self, key: str) -> bool:
        """Check if key exists in cache.

        Args:
            key: Cache key

        Returns:
            True if key exists, False otherwise
        """
        if not self.enabled or not self.client:
            return False

        try:
            exists = await self.client.exists(key)
            return bool(exists > 0)
        except Exception as e:
            logger.warning("redis_exists_error", key=key, error=str(e))
            return False

    async def incr(self, key: str, amount: int = 1) -> int:
        """Increment counter.

        Args:
            key: Cache key
            amount: Amount to increment by

        Returns:
            New value after increment
        """
        if not self.enabled or not self.client:
            return 0

        try:
            value = await self.client.incrby(key, amount)
            return int(value)
        except Exception as e:
            logger.warning("redis_incr_error", key=key, error=str(e))
            return 0

    async def close(self) -> None:
        """Close Redis connection."""
        if self.client:
            try:
                await self.client.close()
                logger.info("redis_closed")
            except Exception as e:
                logger.warning("redis_close_error", error=str(e))


# Convenience functions for common cache patterns
async def cache_generation(
    cache: RedisCache,
    prompt: str,
    params: dict[str, Any],
    ttl: int = 3600,
) -> str:
    """Generate cache key for image generation.

    Args:
        cache: Redis cache instance
        prompt: Generation prompt
        params: Generation parameters
        ttl: Time to live in seconds

    Returns:
        Cache key
    """
    # Create deterministic key from prompt + params
    import hashlib

    param_str = json.dumps(params, sort_keys=True)
    key_data = f"{prompt}:{param_str}"
    key_hash = hashlib.sha256(key_data.encode()).hexdigest()[:16]
    return f"aria:gen:{key_hash}"


async def cache_curation(
    cache: RedisCache,
    image_hash: str,
    ttl: int = 7200,
) -> str:
    """Generate cache key for curation results.

    Args:
        cache: Redis cache instance
        image_hash: Hash of the image
        ttl: Time to live in seconds

    Returns:
        Cache key
    """
    return f"aria:curation:{image_hash}"
