"""Tests for authorization dependencies."""

import sys
from pathlib import Path

import fakeredis
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.middleware.sessions import SessionMiddleware

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# Stub heavy modules before importing routers
sys.modules.setdefault(
    "torch",
    type(
        "torch",
        (),
        {"cuda": type("cuda", (), {"is_available": staticmethod(lambda: False)})},
    ),
)
sys.modules.setdefault("ultralytics", type("ultralytics", (), {"YOLO": object}))
sys.modules.setdefault("deep_sort_realtime", type("ds", (), {}))
sys.modules["deep_sort_realtime.deepsort_tracker"] = type("t", (), {"DeepSort": object})
sys.modules.setdefault("cv2", type("cv2", (), {}))

from routers import settings, visitor  # noqa: E402


def _create_settings_app(tmp_path):
    cfg = {
        "settings_password": "pass",
        "branding": {},
        "enable_face_counting": False,
        "max_capacity": 0,
    }
    r = fakeredis.FakeRedis()
    (tmp_path / "settings.html").write_text("ok")
    settings.init_context(
        cfg,
        {},
        [],
        r,
        str(tmp_path),
        str(tmp_path / "cfg.json"),
        str(tmp_path / "branding.json"),
    )
    app = FastAPI()
    app.add_middleware(SessionMiddleware, secret_key="test")
    app.include_router(settings.router)
    return app


def _create_visitor_app(tmp_path):
    cfg = {"features": {"visitor_mgmt": True}, "track_objects": []}
    r = fakeredis.FakeRedis()
    (tmp_path / "invite_panel.html").write_text("ok")
    visitor.init_context(cfg, r, str(tmp_path), [])
    app = FastAPI()
    app.add_middleware(SessionMiddleware, secret_key="test")
    app.include_router(visitor.router)
    return app


def test_settings_requires_admin(tmp_path):
    app = _create_settings_app(tmp_path)
    client = TestClient(app)
    resp = client.get("/settings", follow_redirects=False)
    assert resp.status_code == 302
    assert resp.headers["location"] == "/login"


def test_invite_requires_viewer(tmp_path):
    app = _create_visitor_app(tmp_path)
    client = TestClient(app)
    resp = client.get("/invite", follow_redirects=False)
    assert resp.status_code == 302
    assert resp.headers["location"] == "/login"
