import asyncio

import fakeredis
import pytest

import routers.cameras as cameras


class DummyTracker:
    def get_debug_stats(self):
        return {"latency": 0.5, "frame_ts": 123.0, "packet_loss": 7}


def _stop_sleep(*args, **kwargs):
    raise StopIteration


def test_health_loop_populates_redis(monkeypatch):
    r = fakeredis.FakeRedis()
    monkeypatch.setattr(cameras, "cams", [{"id": 1}], raising=False)
    monkeypatch.setattr(cameras, "trackers_map", {1: DummyTracker()}, raising=False)
    monkeypatch.setattr(cameras, "redis", r, raising=False)
    monkeypatch.setattr(cameras.asyncio, "sleep", _stop_sleep)
    with pytest.raises(StopIteration):
        asyncio.run(cameras._health_loop())
    data = r.hgetall("camera:1:health")
    assert float(data[b"latency"]) == 0.5
    assert float(data[b"frame_ts"]) == 123.0
    assert int(data[b"packet_loss"]) == 7


def test_collect_health():
    cam = {"id": 1}
    tracker = DummyTracker()
    stats = cameras.collect_health(cam, tracker)
    assert stats == {"latency": 0.5, "frame_ts": 123.0, "packet_loss": 7}


def test_health_loop_handles_missing_tracker(monkeypatch):
    r = fakeredis.FakeRedis()
    monkeypatch.setattr(cameras, "cams", [{"id": 1}, {"id": 2}], raising=False)
    monkeypatch.setattr(cameras, "trackers_map", {1: DummyTracker()}, raising=False)
    monkeypatch.setattr(cameras, "redis", r, raising=False)
    monkeypatch.setattr(cameras.asyncio, "sleep", _stop_sleep)
    with pytest.raises(StopIteration):
        asyncio.run(cameras._health_loop())
    assert r.hgetall("camera:1:health")
    assert r.hgetall("camera:2:health") == {}
