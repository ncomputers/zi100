"""Purpose: Test settings routes module."""

import asyncio
import sys
from pathlib import Path

import fakeredis
import pytest
from fastapi import HTTPException

# stub heavy modules
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

from modules.license import generate_license
from routers import settings


# DummyRequest class encapsulates dummyrequest behavior
class DummyRequest:
    # __init__ routine
    def __init__(self, form=None, json_data=None):
        self.session = {"user": {"role": "admin"}}
        from starlette.datastructures import FormData

        if form is None:
            form = {}
        if isinstance(form, dict):
            form = FormData(list(form.items()))
        self._form = form
        self._json = json_data or {}

    async def form(self):
        return self._form

    async def json(self):
        return self._json


# setup_context routine
def setup_context(tmp_path):
    cfg = {
        "settings_password": "pass",
        "enable_face_counting": False,
        "max_capacity": 0,
        "branding": {},
    }
    r = fakeredis.FakeRedis()
    (tmp_path / "settings.html").write_text("{{ cfg.max_capacity }}")
    settings.init_context(
        cfg,
        {},
        [],
        r,
        str(tmp_path),
        str(tmp_path / "cfg.json"),
        str(tmp_path / "branding.json"),
    )
    return cfg, r


# Test update and export import
def test_update_and_export_import(tmp_path):
    cfg, _ = setup_context(tmp_path)
    req = DummyRequest(
        form={"password": "pass", "max_capacity": "50", "enable_face_counting": "on"}
    )
    res = asyncio.run(settings.update_settings(req))
    assert res["saved"]
    assert cfg["max_capacity"] == 50
    assert cfg["enable_face_counting"] is True

    exp_resp = asyncio.run(settings.export_settings(DummyRequest()))
    import json

    data = json.loads(exp_resp.body.decode())
    assert "config" in data

    imp_req = DummyRequest(json_data={"config": {"max_capacity": 70}, "cameras": []})
    res2 = asyncio.run(settings.import_settings(imp_req))
    assert res2["saved"]
    assert cfg["max_capacity"] == 70


# Test misc endpoints
def test_misc_endpoints(tmp_path):
    cfg, _ = setup_context(tmp_path)
    assert asyncio.run(settings.reset_endpoint()) == {"reset": True}

    lic = generate_license(
        "default_secret", 1, 1, {"face_recognition": True}, client="T"
    )
    resp = asyncio.run(settings.activate_license(DummyRequest(json_data={"key": lic})))
    assert resp["activated"]
    assert cfg["license_key"] == lic

    b_req = DummyRequest(
        form={
            "password": "pass",
            "company_name": "A",
            "site_name": "B",
            "print_layout": "A4",
            "watermark": "on",
        }
    )
    resp2 = asyncio.run(settings.update_settings(b_req))
    assert resp2["saved"]
    assert settings.branding["company_name"] == "A"


# Test persistence on settings page
def test_settings_page_persists_values(tmp_path):
    cfg, _ = setup_context(tmp_path)
    req = DummyRequest(form={"password": "pass", "max_capacity": "25"})
    asyncio.run(settings.update_settings(req))
    resp = asyncio.run(settings.settings_page(DummyRequest()))
    assert resp.context["cfg"]["max_capacity"] == 25


def test_vms_requires_license(tmp_path):
    cfg, _ = setup_context(tmp_path)
    cfg["license_info"] = {"features": {"visitor_mgmt": False}}
    cfg["features"] = {"visitor_mgmt": False}
    req = DummyRequest(form={"password": "pass", "visitor_mgmt": "on"})
    with pytest.raises(HTTPException) as exc:
        asyncio.run(settings.update_settings(req))
    assert exc.value.status_code == 403
    assert cfg["features"]["visitor_mgmt"] is False
