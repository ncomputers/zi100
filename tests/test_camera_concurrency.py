import asyncio

import routers.cameras as cameras


class DummyRequest:
    def __init__(self, data=None):
        self._data = data or {}

    async def json(self):
        return self._data


def _patch(monkeypatch):
    monkeypatch.setattr(cameras, "save_cameras", lambda *a, **k: None)

    async def _no_start(cam_id):
        pass

    monkeypatch.setattr(cameras.camera_manager, "start", _no_start)
    monkeypatch.setattr(cameras, "cfg", {"enable_person_tracking": False})
    monkeypatch.setattr(cameras, "trackers_map", {})
    cameras.cams = []
    cameras.cams_lock = asyncio.Lock()
    cameras.redis = type(
        "R", (), {"hget": lambda *a, **k: "", "hset": lambda *a, **k: None}
    )()


def test_concurrent_add_camera(monkeypatch):
    _patch(monkeypatch)

    async def add(idx):
        req = DummyRequest({"url": f"rtsp://test{idx}"})
        await cameras.add_camera(req)

    async def runner():
        await asyncio.gather(*(add(i) for i in range(2)))

    asyncio.run(runner())
    assert len(cameras.cams) == 2
    assert sorted(cam["id"] for cam in cameras.cams) == [1, 2]


def test_concurrent_toggle_show(monkeypatch):
    _patch(monkeypatch)
    cameras.cams = [
        {
            "id": 1,
            "url": "rtsp://test",
            "type": "rtsp",
            "tasks": [],
            "ppe": False,
            "visitor_mgmt": False,
            "face_recognition": False,
            "enable_face_counting": False,
            "enabled": True,
            "show": False,
            "reverse": False,
            "line_orientation": "vertical",
            "resolution": "720p",
        }
    ]

    async def toggle():
        await cameras.toggle_show(1, DummyRequest())

    async def runner():
        await asyncio.gather(*(toggle() for _ in range(10)))

    asyncio.run(runner())
    assert cameras.cams[0]["show"] is False
