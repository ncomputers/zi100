"""Convenience helpers for storing JSON in Redis.

These helpers mirror ``redis.Redis`` ``get`` and ``set`` but transparently
serialize and deserialize Python objects to JSON. Both synchronous and async
Redis clients are supported.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any


async def get_json(client, key: str, default: Any | None = None) -> Any | None:
    """Return a decoded JSON value stored at ``key``.

    If ``key`` is missing or the stored value is not valid JSON, ``default`` is
    returned instead. Works with both synchronous and asynchronous Redis
    clients.
    """

    data = client.get(key)
    if asyncio.iscoroutine(data):
        data = await data
    if data is None:
        return default
    try:
        return json.loads(data)
    except Exception:
        return default


async def set_json(
    client,
    key: str,
    value: Any,
    expire: int | None = None,
) -> None:
    """Store ``value`` at ``key`` encoded as JSON.

    ``expire`` specifies an optional TTL in seconds. Works with both synchronous
    and asynchronous Redis clients.
    """

    data = json.dumps(value)
    if expire is not None:
        res = client.set(key, data, ex=expire)
    else:
        res = client.set(key, data)
    if asyncio.iscoroutine(res):
        await res
