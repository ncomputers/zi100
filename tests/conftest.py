"""Shared pytest fixtures for app testing."""

import sys
from pathlib import Path

import fakeredis
import pytest
from fakeredis.aioredis import FakeRedis as AsyncFakeRedis
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import types

sys.modules.setdefault(
    "torch",
    types.SimpleNamespace(
        cuda=types.SimpleNamespace(is_available=lambda: False),
        set_num_threads=lambda n: None,
    ),
)
sys.modules.setdefault("ultralytics", types.SimpleNamespace(YOLO=lambda *a, **k: None))
sys.modules.setdefault(
    "deep_sort_realtime",
    types.SimpleNamespace(deepsort_tracker=types.SimpleNamespace(DeepSort=object)),
)
sys.modules.setdefault(
    "deep_sort_realtime.deepsort_tracker", types.SimpleNamespace(DeepSort=object)
)

import threading

import modules.utils as m_utils

m_utils.lock = threading.Lock()


class _DummyCsrf:
    def __init__(self, *a, **k):
        pass

    @classmethod
    def load_config(cls, fn):
        return fn

    def generate_csrf_tokens(self):
        return "token", "token"

    def set_csrf_cookie(self, signed, response):
        return None


class _DummyMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        await self.app(scope, receive, send)


import builtins

builtins.CsrfProtect = _DummyCsrf
builtins.CsrfProtectMiddleware = _DummyMiddleware
sys.modules.setdefault(
    "fastapi_csrf_protect",
    types.SimpleNamespace(
        CsrfProtect=_DummyCsrf, CsrfProtectMiddleware=_DummyMiddleware
    ),
)

import utils.preflight as _preflight

_preflight.check_dependencies = lambda *a, **k: None


@pytest.fixture(autouse=True)
def _stub_probe(monkeypatch):
    import modules.camera_factory as cf

    monkeypatch.setattr(
        cf,
        "probe_stream",
        lambda *a, **k: {
            "metadata": {},
            "transport": "tcp",
            "hwaccel": False,
            "frames": 0,
            "effective_fps": 0.0,
            "trials": [],
        },
    )


@pytest.fixture(scope="session")
def client() -> TestClient:
    mp = pytest.MonkeyPatch()

    import app
    from config import config as cfg
    from utils import preflight
    from utils import redis as redis_utils

    mp.setattr(
        redis_utils,
        "get_sync_client",
        lambda url=None: fakeredis.FakeRedis(decode_responses=True),
    )
    mp.setattr(
        app,
        "get_sync_client",
        lambda url=None: fakeredis.FakeRedis(decode_responses=True),
    )
    mp.setattr(app, "probe_gstreamer", lambda cfg: None, raising=False)

    import asyncio

    mp.setattr(asyncio, "create_task", lambda *a, **k: None)

    async def _fake_get_client(url: str | None = None):
        return AsyncFakeRedis(decode_responses=True)

    mp.setattr(redis_utils, "get_client", _fake_get_client)

    orig = sys.argv
    sys.argv = ["app.py"]
    preflight.check_dependencies = lambda *a, **k: None
    try:
        app.init_app()
    finally:
        sys.argv = orig
    app.app.state.config.setdefault("features", {})["visitor_mgmt"] = True
    cfg.setdefault("features", {})["visitor_mgmt"] = True
    with TestClient(app.app) as c:
        c.post("/login", data={"username": "admin", "password": "rapidadmin"})
        yield c
    mp.undo()


@pytest.fixture(scope="function")
def redis_client():
    client = fakeredis.FakeRedis(decode_responses=True)
    client.flushall()
    yield client
    client.flushall()


@pytest.fixture(autouse=True)
def _flush_redis():
    client = fakeredis.FakeRedis()
    client.flushall()
    yield
    client.flushall()
