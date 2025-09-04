"""Redis helper utilities.

Key naming conventions:
    ``gatepass:pass:{id}``        - main hash storing gate pass fields.
    ``gatepass:signature:{id}``   - HMAC signature for approval tokens.
    ``gatepass:cache:{id}``  - cached JSON representation (24h TTL).

Gate pass hashes and signatures are expired using the visitor log retention
window to limit historical data growth.
"""

import asyncio
import os
from functools import lru_cache
from typing import Optional

import redis as redis_sync
import redis.asyncio as redis_async
from loguru import logger
from redis.exceptions import RedisError

from config import config as shared_config


async def trim_sorted_set(
    client: redis_sync.Redis | redis_async.Redis,
    key: str,
    ts: int,
    retention_secs: Optional[int] = None,
) -> None:
    """Remove entries older than the retention window from a sorted set."""
    if retention_secs is None:
        days = int(shared_config.get("log_retention_days", 30))
        retention_secs = days * 24 * 60 * 60
    res = client.zremrangebyscore(key, 0, ts - retention_secs)
    if asyncio.iscoroutine(res):
        await res


def trim_sorted_set_sync(
    client: redis_sync.Redis | redis_async.Redis,
    key: str,
    ts: int,
    retention_secs: Optional[int] = None,
) -> None:
    """Remove entries older than the retention window from a sorted set."""
    if retention_secs is None:
        days = int(shared_config.get("log_retention_days", 30))
        retention_secs = days * 24 * 60 * 60
    res = client.zremrangebyscore(key, 0, ts - retention_secs)
    if asyncio.iscoroutine(res):
        asyncio.run(res)


# Backwards compatibility alias for deprecated name
trim_sorted_set_async = trim_sorted_set


@lru_cache
def _get_pool(url: str) -> redis_async.ConnectionPool:
    """Return a connection pool for the given URL."""
    return redis_async.ConnectionPool.from_url(url, decode_responses=True)


async def get_client(url: Optional[str] = None) -> redis_async.Redis:
    """Return an async Redis client using a shared connection pool.

    The URL is resolved from the given argument, the shared configuration, or
    the ``REDIS_URL`` environment variable. Responses are decoded to ``str``
    automatically.
    """
    url = (
        url
        or shared_config.get("redis_url")
        or os.getenv("REDIS_URL", "redis://localhost:6379/0")
    )
    pool = _get_pool(url)
    return redis_async.Redis(connection_pool=pool, decode_responses=True)


def get_sync_client(url: Optional[str] = None) -> redis_sync.Redis:
    """Return a synchronous Redis client."""
    url = (
        url
        or shared_config.get("redis_url")
        or os.getenv("REDIS_URL", "redis://localhost:6379/0")
    )
    try:
        client = redis_sync.Redis.from_url(url, decode_responses=True)
        client.ping()
    except (RedisError, OSError) as e:
        logger.error("Failed to connect to Redis at {}: {}", url, e)
        raise
    return client


async def get_camera_overrides(
    client: redis_sync.Redis | redis_async.Redis, cam_id: int
) -> dict[str, str]:
    """Return stored override parameters for a camera.

    The values are fetched atomically from the hash ``camera:{id}`` and can
    include ``url``, ``backend``, ``ffmpeg_flags``, ``pipeline``, ``profile``,
    ``ready_timeout``, ``ready_frames`` and ``ready_duration`` fields.
    When an async Redis client is supplied, ``hgetall`` is awaited to avoid
    ``RuntimeError`` when running inside an event loop.
    """
    data = client.hgetall(f"camera:{cam_id}")
    if asyncio.iscoroutine(data):
        data = await data
    return {k: v for k, v in data.items() if v}


def get_camera_overrides_sync(
    client: redis_sync.Redis | redis_async.Redis, cam_id: int
) -> dict[str, str]:
    """Synchronous wrapper for :func:`get_camera_overrides`."""
    return asyncio.run(get_camera_overrides(client, cam_id))
