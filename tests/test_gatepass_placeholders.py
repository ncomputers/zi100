"""Ensure placeholder strings are not rendered in gate pass views."""

import asyncio
import sys
import types
from pathlib import Path

import fakeredis

# stub qrcode to avoid dependency
sys.modules.setdefault(
    "qrcode",
    types.SimpleNamespace(
        make=lambda data: types.SimpleNamespace(save=lambda *a, **k: None)
    ),
)

from routers import gatepass


class DummyRequest:
    def __init__(self):
        self.session = {"user": {"role": "admin"}}
        self.base_url = "http://testserver/"

    def url_for(self, name, **params):
        return f"/{params.get('path', '')}"


def test_gatepass_view_strips_placeholders(tmp_path):
    cfg = {
        "features": {"visitor_mgmt": True},
        "branding": {},
        "base_url": "http://testserver",
    }
    r = fakeredis.FakeRedis(decode_responses=True)
    templates_dir = Path(__file__).resolve().parents[1] / "templates"
    gatepass.cfg = cfg
    gatepass.init_context(cfg, r, str(templates_dir))
    rec = {
        "gate_id": "GPX",
        "ts": 0,
        "name": "A",
        "phone": ".",
        "email": "work",
        "host": "H",
        "purpose": ".",
        "status": "approved",
    }
    gatepass._save_gatepass(rec)

    resp = asyncio.run(gatepass.gatepass_view("GPX", DummyRequest()))
    body = resp.body.decode()
    assert "work" not in body
    assert ">.<" not in body
    assert "Email</dt>" not in body
