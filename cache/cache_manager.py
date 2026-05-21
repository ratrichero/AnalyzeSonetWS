import asyncio
import time
import json
import hashlib
import logging
from typing import Any, Optional
from cachetools import TTLCache

logger = logging.getLogger(__name__)


class MemoryCacheManager:
    """
    Cache trong RAM – không cần Redis.
    Mỗi (symbol, timeframe) có TTL riêng theo config.
    """

    def __init__(self, cache_ttl: dict):
        self.cache_ttl = cache_ttl          # {"15m": 300, "1h": 900, ...}
        self._store: dict[str, dict] = {}   # key -> {"data": ..., "ts": ..., "ttl": ...}
        self._lock = asyncio.Lock()

    # ------------------------------------------------------------------
    def _make_key(self, symbol: str, timeframe: str, suffix: str = "") -> str:
        raw = f"{symbol}:{timeframe}:{suffix}"
        return hashlib.md5(raw.encode()).hexdigest()

    # ------------------------------------------------------------------
    async def get(self, symbol: str, timeframe: str, suffix: str = "") -> Optional[Any]:
        key = self._make_key(symbol, timeframe, suffix)
        async with self._lock:
            entry = self._store.get(key)
            if entry is None:
                return None
            if time.time() - entry["ts"] > entry["ttl"]:
                del self._store[key]
                logger.debug(f"Cache expired: {symbol} {timeframe} {suffix}")
                return None
            logger.debug(f"Cache hit: {symbol} {timeframe} {suffix}")
            return entry["data"]

    # ------------------------------------------------------------------
    async def set(self, symbol: str, timeframe: str, data: Any, suffix: str = "") -> None:
        key  = self._make_key(symbol, timeframe, suffix)
        ttl  = self.cache_ttl.get(timeframe, 300)
        async with self._lock:
            self._store[key] = {"data": data, "ts": time.time(), "ttl": ttl}
            logger.debug(f"Cache set: {symbol} {timeframe} {suffix} (TTL={ttl}s)")

    # ------------------------------------------------------------------
    async def invalidate(self, symbol: str, timeframe: str, suffix: str = "") -> None:
        key = self._make_key(symbol, timeframe, suffix)
        async with self._lock:
            self._store.pop(key, None)

    # ------------------------------------------------------------------
    async def clear_expired(self) -> int:
        """Dọn dẹp định kỳ – gọi từ background task."""
        now = time.time()
        async with self._lock:
            expired = [k for k, v in self._store.items()
                       if now - v["ts"] > v["ttl"]]
            for k in expired:
                del self._store[k]
        return len(expired)

    # ------------------------------------------------------------------
    def stats(self) -> dict:
        return {"backend": "memory", "entries": len(self._store)}


# ======================================================================
# Facade – chọn backend theo config
# ======================================================================
try:
    import redis.asyncio as aioredis
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False


class RedisCacheManager:
    """Cache Redis – phù hợp khi deploy nhiều process."""

    def __init__(self, redis_url: str, cache_ttl: dict):
        self.cache_ttl = cache_ttl
        self._client   = aioredis.from_url(redis_url, decode_responses=True)

    def _make_key(self, symbol: str, timeframe: str, suffix: str = "") -> str:
        return f"cfa:{symbol}:{timeframe}:{suffix}"

    async def get(self, symbol: str, timeframe: str, suffix: str = "") -> Optional[Any]:
        key = self._make_key(symbol, timeframe, suffix)
        raw = await self._client.get(key)
        if raw is None:
            return None
        return json.loads(raw)

    async def set(self, symbol: str, timeframe: str, data: Any, suffix: str = "") -> None:
        key = self._make_key(symbol, timeframe, suffix)
        ttl = self.cache_ttl.get(timeframe, 300)
        await self._client.setex(key, ttl, json.dumps(data, default=str))

    async def invalidate(self, symbol: str, timeframe: str, suffix: str = "") -> None:
        key = self._make_key(symbol, timeframe, suffix)
        await self._client.delete(key)

    async def clear_expired(self) -> int:
        return 0  # Redis tự xử lý TTL

    def stats(self) -> dict:
        return {"backend": "redis"}


def create_cache_manager(config):
    if config.CACHE_BACKEND == "redis" and REDIS_AVAILABLE:
        logger.info("Using Redis cache backend")
        return RedisCacheManager(config.REDIS_URL, config.CACHE_TTL)
    logger.info("Using in-memory cache backend")
    return MemoryCacheManager(config.CACHE_TTL)