import base64
import io

import fakeredis
from fastapi import FastAPI
from fastapi.testclient import TestClient
from PIL import Image

from config import set_config
from core.config import CONFIG_DEFAULTS
from modules import face_db
from routers import face_db as face_router


def _make_b64() -> str:
    buf = io.BytesIO()
    Image.new("RGB", (10, 10), "white").save(buf, format="JPEG")
    return base64.b64encode(buf.getvalue()).decode()


def _setup_app(monkeypatch) -> TestClient:
    cfg = {**CONFIG_DEFAULTS}
    cfg["features"] = {**CONFIG_DEFAULTS.get("features", {}), "visitor_mgmt": True}
    set_config(cfg)
    r = fakeredis.FakeRedis()
    face_db.init(cfg, r)
    face_router.init_context(cfg, r)
    monkeypatch.setattr(
        face_db,
        "face_app",
        type(
            "A",
            (),
            {"get": lambda self, img: [type("F", (), {"bbox": [0, 0, 10, 10], "pose": [0, 0, 0]})()]},
        )(),
    )
    app = FastAPI()
    app.include_router(face_router.router)
    return TestClient(app)


def test_face_quality(monkeypatch):
    client = _setup_app(monkeypatch)
    resp = client.post("/face_quality", json={"image": _make_b64()})
    assert resp.status_code == 200
    data = resp.json()
    assert "quality" in data and "pose" in data
