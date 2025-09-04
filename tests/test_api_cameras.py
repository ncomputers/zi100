import asyncio
import threading
import time

import fakeredis
from loguru import logger

from routers import cameras
from schemas.camera import CameraCreate, Orientation


def setup_function(func):
    cameras.cams = []
    cameras.trackers_map = {}
    cameras.cfg = {"enable_person_tracking": True}
    cameras.redis = fakeredis.FakeRedis(decode_responses=True)


def test_create_camera_start_async_and_mask(monkeypatch):
    called = threading.Event()

    def fake_start_tracker(*a, **k):
        time.sleep(0.1)
        called.set()

    monkeypatch.setattr(cameras, "start_tracker", fake_start_tracker)
    logs = []
    handle = logger.add(lambda m: logs.append(m), level="INFO")
    cam = CameraCreate(
        name="Cam1",
        url="rtsp://user:pass@example/stream",
        orientation=Orientation.vertical,
        show=True,
        transport="tcp",
        enabled=True,
    )

    async def _run():
        start = time.perf_counter()
        res = await cameras.create_camera_api(cam)
        elapsed = time.perf_counter() - start
        await asyncio.sleep(0.2)
        return res, elapsed

    try:
        result, elapsed = asyncio.run(_run())
    finally:
        logger.remove(handle)
    assert result["id"] == 1
    assert called.wait(1)
    assert elapsed < 0.2
    joined = "".join(logs)
    assert "user:pass" not in joined


def test_create_camera_start_failure_marks_offline(monkeypatch):
    def fake_start_tracker(*a, **k):
        raise RuntimeError("boom")

    monkeypatch.setattr(cameras, "start_tracker", fake_start_tracker)

    cam = CameraCreate(
        name="Cam1",
        url="rtsp://example/stream",
        orientation=Orientation.vertical,
        show=True,
        transport="tcp",
        enabled=True,
    )

    async def _run():
        await cameras.create_camera_api(cam)
        await asyncio.sleep(0.2)

    asyncio.run(_run())
    assert cameras.redis.hget("camera:1", "status") == "offline"


def test_create_camera_without_roi():
    cam = CameraCreate(name="Cam1", url="rtsp://example/stream", inout_count=True)
    res = asyncio.run(cameras.create_camera_api(cam))
    assert "line" not in res
