import subprocess

import fakeredis
from fakeredis.aioredis import FakeRedis as AsyncFakeRedis

import app
import utils.ffmpeg as ffmpeg_utils
from routers import cameras
from utils import redis as redis_utils

app.get_sync_client = lambda url=None: fakeredis.FakeRedis(decode_responses=True)
redis_utils.get_sync_client = lambda url=None: fakeredis.FakeRedis(
    decode_responses=True
)


async def _fake_get_client(url: str | None = None):
    return AsyncFakeRedis(decode_responses=True)


redis_utils.get_client = _fake_get_client


def test_api_camera_test_success(client, monkeypatch):
    monkeypatch.setattr(ffmpeg_utils, "_build_timeout_flags", lambda s: [])

    class CP:
        returncode = 0
        stdout = ""
        stderr = "Stream #0:0: Video: h264, yuvj420p, 640x480\n"

    def fake_run(cmd, stdout=None, stderr=None, text=None, timeout=None, check=False):
        return CP()

    monkeypatch.setattr(subprocess, "run", fake_run)
    resp = client.post(
        "/api/cameras/test", json={"url": "rtsp://example", "transport": "tcp"}
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    assert data["width"] == 640
    assert data["height"] == 480
    assert data["codec"] == "h264"


def test_api_camera_test_masks_logs(client, monkeypatch):
    monkeypatch.setattr(ffmpeg_utils, "_build_timeout_flags", lambda s: [])

    class CP:
        returncode = 1
        stdout = ""
        stderr = "rtsp://user:pass@example\n401 Unauthorized\n"

    def fake_run(cmd, stdout=None, stderr=None, text=None, timeout=None, check=False):
        return CP()

    monkeypatch.setattr(subprocess, "run", fake_run)
    resp = client.post(
        "/api/cameras/test",
        json={"url": "rtsp://user:pass@example", "transport": "tcp"},
    )
    assert resp.status_code == 400
    data = resp.json()
    assert data["ok"] is False
    tail = data["stderr_tail"]
    assert "***:***@" in tail
    assert "user:pass@" not in tail
    assert data["error"] == "AUTH_FAILED"
    assert data["hints"] == ["Verify camera credentials"]


def test_activate_camera_success(client, monkeypatch):
    client.post("/api/cameras", json={"name": "Cam2", "url": "rtsp://example"})

    called = {}
    monkeypatch.setattr(
        cameras.camera_manager, "start", lambda cid: called.setdefault("cid", cid)
    )

    resp = client.post("/api/cameras/2/activate")
    assert resp.status_code == 200
    data = resp.json()
    assert data["activated"] is True
    assert called["cid"] == 2
