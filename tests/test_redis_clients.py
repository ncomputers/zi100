import asyncio
import fakeredis
from fakeredis.aioredis import FakeRedis as AsyncFakeRedis

from utils import redis as redis_utils


def test_get_sync_client_in_loop(monkeypatch):
    fake = fakeredis.FakeRedis(decode_responses=True)
    monkeypatch.setattr(redis_utils.redis_sync.Redis, "from_url", lambda *a, **k: fake)

    async def run():
        client = redis_utils.get_sync_client()
        client.set("k", "v")
        return client.get("k")

    result = asyncio.run(run())
    assert result == "v"


def test_get_client_in_loop(monkeypatch):
    fake = AsyncFakeRedis(decode_responses=True)
    monkeypatch.setattr(redis_utils, "_get_pool", lambda url: None)
    monkeypatch.setattr(redis_utils.redis_async, "Redis", lambda *a, **k: fake)

    async def run():
        client = await redis_utils.get_client()
        await client.set("k", "v")
        return await client.get("k")

    result = asyncio.run(run())
    assert result == "v"
