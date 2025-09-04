import asyncio
import time

import pytest

from routers import cameras


class DummyRequest:
    def __init__(self, data):
        self._data = data

    async def json(self):
        return self._data

    async def is_disconnected(self):
        return False


class SlowStream:
    def __init__(self, *a, **k):
        pass

    def read(self):
        time.sleep(0.5)
        return False, None

    def release(self):
        pass


def test_cancel_prior_probe(monkeypatch):
    monkeypatch.setattr(cameras, "cfg", {})
    monkeypatch.setattr(cameras, "TEST_CAMERA_TRANSPORT", {})
    monkeypatch.setattr(cameras, "TEST_CAMERA_PROBES", {})
    monkeypatch.setattr(cameras, "FFmpegCameraStream", SlowStream)
    monkeypatch.setattr(cameras, "GstCameraStream", SlowStream)

    async def _run():
        req1 = DummyRequest({"url": "rtsp://demo"})
        task1 = asyncio.create_task(cameras.test_camera(req1))
        await asyncio.sleep(0.1)

        req2 = DummyRequest({"url": "rtsp://demo"})
        task2 = asyncio.create_task(cameras.test_camera(req2))

        resp2 = await task2
        assert resp2.status_code == 400

        with pytest.raises(asyncio.CancelledError):
            await task1

    asyncio.run(_run())
