"""Purpose: Test branding module."""

import asyncio
import io
import json
import sys
import time
from pathlib import Path

import fakeredis
from fastapi import FastAPI
from fastapi.testclient import TestClient
from PIL import Image
from starlette.staticfiles import StaticFiles

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

from routers import settings


# setup routine
def setup(tmp_path):
    cfg = {"settings_password": "pass", "branding": {}}
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
    return cfg, r


# make_image routine
def make_image():
    img = Image.new("RGB", (200, 80), "red")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf


# Test logo upload
def test_logo_upload(tmp_path, monkeypatch):
    cfg, _ = setup(tmp_path)
    monkeypatch.setattr(settings, "LOGO_DIR", tmp_path / "static/logos")
    settings.LOGO_DIR.mkdir(parents=True)
    monkeypatch.setattr(settings, "require_roles", lambda r, roles: {"role": "admin"})
    app = FastAPI()
    app.post("/settings")(settings.update_settings)
    app.mount("/static", StaticFiles(directory=settings.LOGO_DIR.parent), name="static")
    client = TestClient(app)

    buf = make_image()
    files = {"logo": ("logo.png", buf, "image/png")}
    resp = client.post(
        "/settings", data={"password": "pass", "company_name": "A"}, files=files
    )
    assert resp.status_code == 200
    filename = cfg["branding"]["company_logo"]
    assert filename.endswith(".png")
    url1 = cfg["branding"]["company_logo_url"]
    assert url1.startswith("/static/logos/")
    assert (
        json.loads(Path(tmp_path / "branding.json").read_text())["company_logo"]
        == filename
    )
    assert client.get(url1.split("?")[0]).status_code == 200

    buf.seek(0)
    time.sleep(1)
    resp2 = client.post(
        "/settings", data={"password": "pass", "company_name": "A"}, files=files
    )
    url2 = cfg["branding"]["company_logo_url"]
    assert url1 != url2


def test_logo_invalid_file(tmp_path, monkeypatch):
    cfg, _ = setup(tmp_path)
    monkeypatch.setattr(settings, "LOGO_DIR", tmp_path / "static/logos")
    settings.LOGO_DIR.mkdir(parents=True)
    monkeypatch.setattr(settings, "require_roles", lambda r, roles: {"role": "admin"})
    app = FastAPI()
    app.post("/settings/branding")(settings.branding_update)
    client = TestClient(app)

    files = {"logo": ("bad.txt", io.BytesIO(b"not an image"), "text/plain")}
    resp = client.post("/settings/branding", data={"company_name": "A"}, files=files)
    assert resp.status_code == 400


def test_logo_too_large(tmp_path, monkeypatch):
    cfg, _ = setup(tmp_path)
    monkeypatch.setattr(settings, "LOGO_DIR", tmp_path / "static/logos")
    settings.LOGO_DIR.mkdir(parents=True)
    monkeypatch.setattr(settings, "require_roles", lambda r, roles: {"role": "admin"})
    app = FastAPI()
    app.post("/settings/branding")(settings.branding_update)
    client = TestClient(app)

    big = io.BytesIO(b"a" * (1_000_001))
    files = {"logo": ("big.png", big, "image/png")}
    resp = client.post("/settings/branding", data={"company_name": "A"}, files=files)
    assert resp.status_code == 400
