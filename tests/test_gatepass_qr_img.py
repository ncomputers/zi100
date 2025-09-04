import asyncio
import base64
import json
import types

import fakeredis

from routers import gatepass


class DummyRequest:
    def __init__(self):
        self.session = {"user": {"role": "admin"}}
        self.base_url = "http://testserver/"

    def url_for(self, name: str, **params):
        return "/" + name


def test_gatepass_create_returns_qr_img(tmp_path, monkeypatch):
    cfg = {"features": {"visitor_mgmt": True}, "base_url": "http://testserver"}
    r = fakeredis.FakeRedis(decode_responses=True)
    gatepass.init_context(cfg, r, str(tmp_path))

    monkeypatch.setattr(
        gatepass, "save_base64_to_image", lambda *a, **k: str(tmp_path / "img.jpg")
    )
    monkeypatch.setattr(gatepass, "add_face_to_known_db", lambda **k: None)
    monkeypatch.setattr(
        gatepass,
        "face_db",
        types.SimpleNamespace(insert=lambda *a, **k: None),
        raising=False,
    )
    monkeypatch.setattr(gatepass.visitor_db, "init_db", lambda r: None)
    monkeypatch.setattr(gatepass.visitor_db, "save_host", lambda *a, **k: None)
    monkeypatch.setattr(gatepass.visitor, "invalidate_host_cache", lambda: None)
    captured = {}

    def fake_save_visitor(name, email, phone, visitor_type, company_name, photo_url):
        captured["photo_url"] = photo_url
        return "VID"

    monkeypatch.setattr(gatepass.visitor, "_save_visitor_master", fake_save_visitor)

    dummy = "data:image/jpeg;base64," + base64.b64encode(b"img").decode()
    resp = asyncio.run(
        gatepass.gatepass_create(
            DummyRequest(),
            name="A",
            phone="1",
            email="",
            host="H",
            purpose="P",
            visitor_type="Official",
            host_department="",
            company_name="C",
            photo=None,
            captured=dummy,
            invite_id="",
            valid_to="",
            needs_approval="off",
            approver_email="",
        )
    )
    data = json.loads(resp.body)
    assert data["qr_img"].startswith("data:image")
    assert "?v=" in captured.get("photo_url", "")
