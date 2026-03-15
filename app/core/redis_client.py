"""
Redis async client with connection management and health checks.
"""
import json
from typing import Any, Optional
import structlog
import redis.asyncio as aioredis
from redis.asyncio import Redis

from app.core.config import settings

logger = structlog.get_logger()

_redis_client: Optional[Redis] = None


async def init_redis() -> None:
    """Initialize Redis connection pool."""
    global _redis_client
    _redis_client = aioredis.from_url(
        settings.REDIS_URL,
        encoding="utf-8",
        decode_responses=True,
        max_connections=50,
        socket_connect_timeout=5,
        socket_keepalive=True,
        health_check_interval=30,
    )
    # Verify connection
    await _redis_client.ping()
    logger.info("Redis connected", url=settings.REDIS_URL.split("@")[-1])


async def close_redis() -> None:
    """Close Redis connections."""
    global _redis_client
    if _redis_client:
        await _redis_client.aclose()
        _redis_client = None
        logger.info("Redis connection closed")


def get_redis() -> Redis:
    """Get Redis client instance."""
    if _redis_client is None:
        raise RuntimeError("Redis not initialized. Call init_redis() first.")
    return _redis_client


async def check_redis_health() -> bool:
    """Check Redis connectivity."""
    try:
        client = get_redis()
        await client.ping()
        return True
    except Exception as e:
        logger.error("Redis health check failed", error=str(e))
        return False


class CacheService:
    """High-level cache operations with JSON serialization."""

    def __init__(self, prefix: str = "sc", ttl: int = settings.REDIS_CACHE_TTL):
        self.prefix = prefix
        self.ttl = ttl

    def _key(self, key: str) -> str:
        return f"{self.prefix}:{key}"

    async def get(self, key: str) -> Optional[Any]:
        client = get_redis()
        value = await client.get(self._key(key))
        if value is None:
            return None
        try:
            return json.loads(value)
        except (json.JSONDecodeError, TypeError):
            return value

    async def set(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        client = get_redis()
        serialized = json.dumps(value, default=str)
        await client.setex(self._key(key), ttl or self.ttl, serialized)

    async def delete(self, key: str) -> None:
        client = get_redis()
        await client.delete(self._key(key))

    async def delete_pattern(self, pattern: str) -> int:
        client = get_redis()
        keys = await client.keys(self._key(pattern))
        if keys:
            return await client.delete(*keys)
        return 0

    async def exists(self, key: str) -> bool:
        client = get_redis()
        return bool(await client.exists(self._key(key)))

    async def incr(self, key: str, ttl: Optional[int] = None) -> int:
        client = get_redis()
        full_key = self._key(key)
        value = await client.incr(full_key)
        if ttl and value == 1:  # Set TTL only on first increment
            await client.expire(full_key, ttl)
        return value

    async def get_or_set(self, key: str, factory, ttl: Optional[int] = None) -> Any:
        """Get from cache or compute and store."""
        cached = await self.get(key)
        if cached is not None:
            return cached
        value = await factory()
        await self.set(key, value, ttl)
        return value
