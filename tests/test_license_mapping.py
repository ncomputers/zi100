"""Purpose: Test license mapping module."""

import sys
from pathlib import Path

import fakeredis
from bs4 import BeautifulSoup
from fastapi import FastAPI
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

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

from routers import cameras


# setup routine
def setup(tmp_path, features):
    cfg = {
        "features": features,
        "license_info": {"features": features},
        "branding": {},
        "logo_url": "",
        "logo2_url": "",
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
    cameras.init_context(cfg, cams, {}, r, str(ROOT / "templates"))
    from config import set_config

    set_config(cfg)
    app = FastAPI()
    app.get("/cameras")(cameras.cameras_page)
    app.post("/cameras/{cam_id}/ppe")(cameras.toggle_ppe)
    app.post("/cameras/{cam_id}/face_recog")(cameras.toggle_face_recog)
    return app, cams


# Test license mapping
def test_license_mapping(tmp_path, monkeypatch):
    app, cams = setup(
        tmp_path,
        {"ppe_detection": False, "visitor_mgmt": True, "face_recognition": True},
    )
    monkeypatch.setattr(cameras, "require_roles", lambda r, roles: {"role": "admin"})
    client = TestClient(app)

    html = client.get("/cameras").text
    soup = BeautifulSoup(html, "html.parser")
    row = soup.find("tbody").find("tr")
    ppe_input = row.find("input", {"data-feature": "ppe_detection"})
    face_input = row.find("input", {"data-feature": "face_recognition"})
    assert ppe_input is None or ppe_input.has_attr("disabled")
    assert face_input is not None and not face_input.has_attr("disabled")

    assert client.post("/cameras/1/ppe").status_code == 403
    resp = client.post("/cameras/1/face_recog")
    assert resp.status_code == 200
    assert cams[0]["face_recognition"] is True
