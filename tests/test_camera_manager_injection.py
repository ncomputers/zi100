import routers.cameras as cameras
from schemas.camera import CameraCreate


class DummyManager:
    def __init__(self):
        self.started = None

    async def start(self, cam_id: int):  # pragma: no cover - simple stub
        self.started = cam_id

    async def restart(self, cam_id: int):
        self.started = cam_id

    async def refresh_flags(self, cam_id: int):
        self.started = cam_id


def test_manager_injection(client, monkeypatch):
    monkeypatch.setattr(cameras, "cams", [])
    monkeypatch.setattr(cameras, "save_cameras", lambda *a, **k: None)
    monkeypatch.setattr(cameras, "cfg", {"enable_person_tracking": True})
    monkeypatch.setattr(cameras, "trackers_map", {})
    dummy = DummyManager()
    client.app.dependency_overrides[cameras.get_camera_manager] = lambda: dummy
    cam = CameraCreate(url="rtsp://x", enabled=True, name="c1")

    resp = client.post("/api/cameras", json=cam.dict())
    client.app.dependency_overrides = {}
    assert resp.status_code == 200
    assert dummy.started == resp.json()["id"]
