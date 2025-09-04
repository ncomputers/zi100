import asyncio

import fakeredis
import pytest
from fakeredis.aioredis import FakeRedis as AsyncFakeRedis

import app
from routers import cameras
from utils import redis as redis_utils


@pytest.fixture(scope="session", autouse=True)
def _patch_redis():  # pragma: no cover - test setup helper
    mp = pytest.MonkeyPatch()
    mp.setattr(
        redis_utils,
        "get_sync_client",
        lambda url=None: fakeredis.FakeRedis(decode_responses=True),
    )

    async def _fake_get_client(url: str | None = None):
        return AsyncFakeRedis(decode_responses=True)

    mp.setattr(redis_utils, "get_client", _fake_get_client)
    mp.setattr(
        app,
        "get_sync_client",
        lambda url=None: fakeredis.FakeRedis(decode_responses=True),
    )
    yield
    mp.undo()


class _DummyProc:
    def __init__(self):
        self.returncode = None

    async def communicate(self):  # pragma: no cover - simple helper
        self.returncode = 0
        return b"frame", b""

    def kill(self):  # pragma: no cover - simple helper
        self.returncode = -9

    async def wait(self):  # pragma: no cover - simple helper
        return 0


async def _fake_exec(*cmd, **kw):  # pragma: no cover - used in tests
    return _DummyProc()


def test_api_camera_test_returns_token(client, monkeypatch):
    monkeypatch.setattr(cameras, "PREVIEW_TOKENS", {})
    monkeypatch.setattr(
        cameras,
        "probe_rtsp",
        lambda *a, **k: {
            "metadata": {"width": 640, "height": 480},
            "effective_fps": 15.0,
        },
    )
    r = client.post("/api/cameras/test", json={"url": "rtsp://demo"})
    assert r.status_code == 200
    data = r.json()
    assert data["token"] in cameras.PREVIEW_TOKENS
    assert data["width"] == 640
    assert data["height"] == 480
    assert data["fps_estimate"] == 15.0


def test_api_camera_preview_frame(client, monkeypatch):
    monkeypatch.setattr(cameras, "PREVIEW_TOKENS", {})
    monkeypatch.setattr(asyncio, "create_subprocess_exec", _fake_exec)
    monkeypatch.setattr(
        cameras,
        "probe_rtsp",
        lambda *a, **k: {
            "metadata": {"width": 640, "height": 480},
            "effective_fps": 15.0,
        },
    )
    r = client.post("/api/cameras/test", json={"url": "rtsp://demo"})
    token = r.json()["token"]
    resp = client.get(f"/api/cameras/preview?token={token}")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "image/jpeg"
    assert resp.content == b"frame"


class _FullSem:
    def locked(self):  # pragma: no cover - simple helper
        return True

    async def acquire(self):  # pragma: no cover - simple helper
        pass

    def release(self):  # pragma: no cover - simple helper
        pass


def test_api_camera_preview_limit(client, monkeypatch):
    monkeypatch.setattr(cameras, "PREVIEW_TOKENS", {})
    monkeypatch.setattr(cameras, "preview_semaphore", _FullSem())
    monkeypatch.setattr(
        cameras,
        "probe_rtsp",
        lambda *a, **k: {
            "metadata": {"width": 640, "height": 480},
            "effective_fps": 15.0,
        },
    )
    r = client.post("/api/cameras/test", json={"url": "rtsp://demo"})
    token = r.json()["token"]
    resp = client.get(f"/api/cameras/preview?token={token}")
    assert resp.status_code == 409
    assert resp.json()["error"] == "Please close other previews"


def test_api_camera_preview_rejects_undefined(client):
    resp = client.get("/api/cameras/preview?token=undefined")
    assert resp.status_code == 400
