import asyncio
from datetime import datetime

import fakeredis
import numpy as np

from models import camera as camera_model
from models.camera import Orientation, Transport, get_camera
from routers import cameras


def _patch(monkeypatch):
    r = fakeredis.FakeRedis()
    monkeypatch.setattr(cameras, "save_cameras", lambda *a, **k: None)
    monkeypatch.setattr(cameras, "start_tracker", lambda *a, **k: None)
    monkeypatch.setattr(
        cameras, "cfg", {"license_info": {"features": {}}}, raising=False
    )
    monkeypatch.setattr(cameras, "redis", r, raising=False)
    monkeypatch.setattr(cameras, "trackers_map", {}, raising=False)

    def _dummy_create_task(coro, *a, **k):
        if hasattr(coro, "close"):
            coro.close()
        return None

    monkeypatch.setattr(cameras.asyncio, "create_task", _dummy_create_task)

    class DummyStream:
        def __init__(self, *a, **k):
            DummyStream.kwargs = k

        def wait_first_frame(self, *a, **k):
            return np.zeros((1, 1, 3), dtype=np.uint8)

        def read(self):
            return True, np.zeros((1, 1, 3), dtype=np.uint8)

        def release(self):
            pass

    class DummyCap:
        def __init__(self, *a, **k):
            pass

        def read(self):
            return True, np.zeros((1, 1, 3), dtype=np.uint8)

        def release(self):
            pass

    monkeypatch.setattr(cameras, "FFmpegCameraStream", DummyStream)
    monkeypatch.setattr(cameras, "GstCameraStream", DummyStream)
    monkeypatch.setattr(cameras.cv2, "VideoCapture", DummyCap)
    monkeypatch.setattr(
        cameras.cv2,
        "imencode",
        lambda ext, frame: (True, np.array([1], dtype=np.uint8)),
    )

    monkeypatch.setattr(camera_model, "get_sync_client", lambda url=None: r)


def test_camera_record_persist_and_defaults(monkeypatch):
    _patch(monkeypatch)
    cameras.cams = []

    class DummyReq:
        async def json(self):
            return {"name": "CamDB", "url": "rtsp://demo", "type": "rtsp"}

    class DummyManager:
        async def start(self, cam_id):
            return None

    resp = asyncio.run(cameras.add_camera(DummyReq(), manager=DummyManager()))
    assert resp["added"] is True
    cam_uuid = resp["camera"]["uuid"]
    row = get_camera(cam_uuid)
    assert row is not None
    assert row.name == "CamDB"
    assert row.orientation == Orientation.vertical
    assert row.transport == Transport.tcp
    assert row.enabled is True
    assert row.site_id == 1
    assert isinstance(row.created_at, datetime)
    assert isinstance(row.updated_at, datetime)
