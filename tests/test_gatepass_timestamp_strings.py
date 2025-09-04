"""Ensure gatepass routes handle string timestamps from redis."""

import asyncio
from pathlib import Path

import fakeredis

from routers import gatepass


class DummyRequest:
    def __init__(self):
        self.session = {"user": {"role": "admin"}}
        self.base_url = "http://testserver/"

    def url_for(self, name, **params):  # pragma: no cover - not used
        return "/" + params.get("path", "")


def test_gatepass_view_handles_string_timestamps(tmp_path):
    cfg = {"features": {"visitor_mgmt": True}}
    r = fakeredis.FakeRedis(decode_responses=True)
    (tmp_path / "gatepass_view.html").write_text("x")
    gatepass.init_context(cfg, r, str(tmp_path))
    rec = {
        "gate_id": "GPX",
        "ts": "100",
        "valid_from": "100",
        "valid_to": "200",
        "name": "A",
        "phone": "1",
        "email": "",
        "host": "H",
        "purpose": "P",
        "status": "approved",
    }
    r.hset(f"gatepass:pass:{rec['gate_id']}", mapping=rec)
    resp = asyncio.run(gatepass.gatepass_view("GPX", DummyRequest()))
    assert resp.status_code == 200

