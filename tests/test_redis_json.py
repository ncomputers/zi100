import asyncio

from fakeredis.aioredis import FakeRedis

from utils.redis_json import get_json, set_json


def test_set_and_get_json():
    client = FakeRedis(decode_responses=True)

    async def run():
        value = {"a": 1, "b": [1, 2]}
        await set_json(client, "k", value)
        return await get_json(client, "k")

    result = asyncio.run(run())
    assert result == {"a": 1, "b": [1, 2]}


def test_get_json_default_and_ttl():
    client = FakeRedis(decode_responses=True)

    async def run():
        default = {"missing": True}
        missing = await get_json(client, "missing", default=default)
        await set_json(client, "temp", {"x": 1}, expire=1)
        ttl = await client.ttl("temp")
        await asyncio.sleep(1.1)
        expired = await get_json(client, "temp")
        return missing, ttl, expired

    missing, ttl, expired = asyncio.run(run())
    assert missing == {"missing": True}
    assert 0 < ttl <= 1
    assert expired is None
