import asyncio
import sys
from pathlib import Path

import fakeredis
import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from routers import cameras  # noqa: E402

pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend():
    return "asyncio"


class Buf:
    def __init__(self, data: bytes = b"img"):
        self._data = data

    def tobytes(self) -> bytes:  # pragma: no cover - trivial
        return self._data


class CV2Stub:
    CAP_PROP_FRAME_WIDTH = 3
    CAP_PROP_FRAME_HEIGHT = 4
    CAP_PROP_FPS = 5

    @staticmethod
    def imencode(ext, frame):  # pragma: no cover - trivial
        return True, Buf()


@pytest.fixture
async def api_client(tmp_path, monkeypatch):
    cfg = {}
    cams = []
    r = fakeredis.FakeRedis()
    cameras.init_context(cfg, cams, {}, r, str(tmp_path))
    monkeypatch.setattr(cameras, "require_roles", lambda r, roles: {"role": "admin"})
    app = FastAPI()
    app.include_router(cameras.router)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client, r, cams


async def test_add_camera_persists_and_activates(api_client, monkeypatch):

    client, r, cams = api_client

    def ok_probe(*a, **k):
        return {"ok": True}

    monkeypatch.setattr(cameras, "check_rtsp", ok_probe)

    class StreamStub:
        def __init__(self, *a, **k):
            self.last_status = "ok"
            self.last_error = ""
            self.last_hint = ""
            self.last_stderr = ""
            self.last_command = "cmd"

        def read(self):
            return True, object()

        def release(self):
            pass

    monkeypatch.setattr(cameras, "FFmpegCameraStream", StreamStub)
    monkeypatch.setattr(cameras, "cv2", CV2Stub)

    started = {}

    async def fake_start(cam_id):
        started["id"] = cam_id

    monkeypatch.setattr(cameras.camera_manager, "start", fake_start)

    resp = await client.post(
        "/api/cameras", json={"name": "Cam", "url": "rtsp://example"}
    )
    assert resp.status_code == 200
    cam_id = resp.json()["id"]
    assert len(cams) == 1
    assert r.get("cameras") is not None
    assert started == {}

    resp = await client.post(f"/api/cameras/{cam_id}/activate")
    assert resp.status_code == 200
    assert resp.json()["activated"] is True
    assert started["id"] == cam_id
