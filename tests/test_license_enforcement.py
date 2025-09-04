"""Purpose: Test license enforcement module."""

import asyncio
import sys
from pathlib import Path

import fakeredis
from fastapi import FastAPI
from fastapi.testclient import TestClient

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

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from routers import cameras, settings


# setup_app routine
def setup_app(tmp_path, enabled: bool):
    cfg = {
        "features": {
            "ppe_detection": enabled,
            "visitor_mgmt": True,
            "face_recognition": True,
        }
    }
    cams = [
        {
            "id": 1,
            "name": "C1",
            "url": "u",
            "type": "http",
            "tasks": [],
            "ppe": False,
            "visitor_mgmt": False,
            "face_recognition": False,
        }
    ]
    r = fakeredis.FakeRedis()
    cameras.init_context(cfg, cams, {}, r, str(tmp_path))
    from config import set_config

    set_config(cfg)
    app = FastAPI()
    app.post("/cameras/{cam_id}/ppe")(cameras.toggle_ppe)
    return app, cams


# DummyRequest class encapsulates minimal request behavior for settings
class DummyRequest:
    """Minimal request object providing form data and admin session."""

    def __init__(self, form=None):
        self.session = {"user": {"role": "admin"}}
        from starlette.datastructures import FormData

        form = form or {}
        self._form = FormData(list(form.items()))

    async def form(self):
        return self._form


# Test ppe toggle requires license
def test_ppe_toggle_requires_license(tmp_path, monkeypatch):
    app, _ = setup_app(tmp_path, False)
    monkeypatch.setattr(cameras, "require_roles", lambda r, roles: {"role": "admin"})
    client = TestClient(app)
    resp = client.post("/cameras/1/ppe")
    assert resp.status_code == 403

    app2, cams2 = setup_app(tmp_path, True)
    monkeypatch.setattr(cameras, "require_roles", lambda r, roles: {"role": "admin"})
    client2 = TestClient(app2)
    resp2 = client2.post("/cameras/1/ppe")
    assert resp2.status_code == 200
    assert cams2[0]["ppe"] is True


# Test settings update cannot enable unlicensed features
def test_update_settings_respects_license(tmp_path, monkeypatch):
    cfg = {
        "settings_password": "pass",
        "branding": {},
        "features": {"visitor_mgmt": False},
        "license_info": {"features": {"visitor_mgmt": False}},
    }
    r = fakeredis.FakeRedis()
    settings.init_context(
        cfg,
        {},
        [],
        r,
        str(tmp_path),
        str(tmp_path / "cfg.json"),
        str(tmp_path / "branding.json"),
    )
    # Bypass role check and background profiler
    monkeypatch.setattr(settings, "require_roles", lambda r, roles: {"role": "admin"})
    import modules.profiler as profiler

    monkeypatch.setattr(profiler, "start_profiler", lambda c: None)

    captured = {}
    import config as global_config

    def fake_set_config(c):
        captured.update(c)

    monkeypatch.setattr(global_config, "set_config", fake_set_config)

    req = DummyRequest(form={"password": "pass", "visitor_mgmt": "on"})
    res = asyncio.run(settings.update_settings(req))
    assert res["saved"]
    assert cfg["features"]["visitor_mgmt"] is False
    assert captured["features"]["visitor_mgmt"] is False
