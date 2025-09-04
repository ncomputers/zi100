import importlib
import json

import pytest
from redis.exceptions import ConnectionError as RedisConnectionError

import core.stats

pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
def dashboard_module():
    import modules.utils as mutils

    mutils.lock = object()
    return importlib.import_module("routers.dashboard")


class StreamRedisMock:
    def __init__(self):
        self.calls = 0

    def xread(self, streams, block=0, count=0):
        self.calls += 1
        if self.calls == 1:
            return [("stats_stream", [(b"1-0", {b"data": b'{"v":1}'})])]
        return []


async def test_stats_event_source_stream(monkeypatch, dashboard_module):
    monkeypatch.setattr(core.stats, "gather_stats", lambda t, r: {"init": True})
    redis = StreamRedisMock()
    gen = dashboard_module.stats_event_source(redis, {}, True)
    first = await anext(gen)
    assert json.loads(first[6:-2]) == {"init": True}
    second = await anext(gen)
    assert json.loads(second[6:-2]) == {"v": 1}
    ping = await anext(gen)
    assert ping == ": ping\n\n"
    await gen.aclose()


class PubSubMock:
    def __init__(self, messages):
        self.messages = messages

    def subscribe(self, channel):
        pass

    def listen(self):
        for msg in self.messages:
            yield msg
        raise RedisConnectionError

    def ping(self):
        pass

    def close(self):
        pass


class RedisPubSubMock:
    def __init__(self, messages):
        self.messages = messages

    def pubsub(self, ignore_subscribe_messages=True):
        return PubSubMock(self.messages)


async def test_stats_event_source_pubsub(monkeypatch, dashboard_module):
    monkeypatch.setattr(core.stats, "gather_stats", lambda t, r: {"init": True})
    redis = RedisPubSubMock([{"type": "message", "data": b'{"v":2}'}])
    gen = dashboard_module.stats_event_source(redis, {}, False)
    first = await anext(gen)
    assert json.loads(first[6:-2]) == {"init": True}
    second = await anext(gen)
    assert json.loads(second[6:-2]) == {"v": 2}
    await gen.aclose()
