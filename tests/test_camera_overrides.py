import asyncio
from fakeredis.aioredis import FakeRedis as AsyncRedis

from utils.redis import get_camera_overrides, get_camera_overrides_sync


def test_get_camera_overrides_async():
    r = AsyncRedis(decode_responses=True)

    async def run() -> dict[str, str]:
        await r.hset("camera:1", mapping={"url": "stream", "profile": ""})
        return await get_camera_overrides(r, 1)

    overrides = asyncio.run(run())
    assert overrides == {"url": "stream"}


def test_get_camera_overrides_sync(redis_client):
    r = redis_client
    r.hset("camera:2", mapping={"backend": "ffmpeg", "profile": ""})
    overrides = get_camera_overrides_sync(r, 2)
    assert overrides == {"backend": "ffmpeg"}


def test_get_camera_overrides_sync_in_loop(redis_client):
    r = redis_client
    r.hset("camera:3", mapping={"url": "stream"})

    async def run() -> dict[str, str]:
        return await asyncio.to_thread(get_camera_overrides_sync, r, 3)

    overrides = asyncio.run(run())
    assert overrides == {"url": "stream"}
