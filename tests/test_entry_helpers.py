"""Tests for entry module helper functions."""

import base64
import json
import sys
from pathlib import Path

import fakeredis
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from modules import visitor_db  # noqa: E402
from routers import entry  # noqa: E402


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.mark.anyio
async def test_parse_visitor_form(monkeypatch):
    r = fakeredis.FakeRedis()
    visitor_db.init_db(r)
    entry.redis = r
    form = entry.RegisterVisitorForm(name="Alice", phone="123", host="Bob")
    form.captured = "data:image/jpeg;base64," + base64.b64encode(b"img").decode()

    called = {}

    def fake_get_or_create(name, phone, email="", org="", photo=""):
        called["visitor"] = (name, phone, photo)
        return "VID"

    def fake_save_host(name, email=""):
        called["host"] = name

    monkeypatch.setattr(visitor_db, "get_or_create_visitor", fake_get_or_create)
    monkeypatch.setattr(visitor_db, "save_host", fake_save_host)

    parsed = await entry._parse_visitor_form(form, None)
    assert parsed["entry"]["visitor_id"] == "VID"
    assert r.zcard("vms_logs") == 1
    assert called["host"] == "Bob"


@pytest.mark.anyio
async def test_update_visit_request(monkeypatch):
    r = fakeredis.FakeRedis()
    req = {"id": "1", "phone": "123", "status": "pending", "email": "a@b", "ts": 1}
    r.zadd("visit_requests", {json.dumps(req): req["ts"]})

    sent = {}

    monkeypatch.setattr(
        entry, "send_email", lambda s, b, to, cfg: sent.update({"to": to})
    )

    form = entry.RegisterVisitorForm(name="Alice", phone="123")
    await entry._update_visit_request(r, form, "GP1")

    updated = json.loads(r.zrange("visit_requests", 0, -1)[0])
    assert updated["status"] == "arrived"
    assert updated["gate_id"] == "GP1"
    assert sent["to"] == ["a@b"]


def test_add_face_to_db(monkeypatch):
    calls = {}

    def fake_add_face(img, gid, threshold=1.1):
        calls["args"] = (img, gid, threshold)
        return True

    from modules import face_db

    monkeypatch.setattr(face_db, "add_face_if_single_detected", fake_add_face)
    entry._add_face_to_db(b"data", "GP1")
    assert calls["args"][1] == "GP1"
