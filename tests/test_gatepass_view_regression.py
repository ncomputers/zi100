import asyncio
import base64
from pathlib import Path

import fakeredis

from routers import gatepass


class DummyRequest:
    def __init__(self):
        self.session = {"user": {"role": "admin"}}
        self.base_url = "http://testserver/"

    def url_for(self, name, **params):
        if name == "static":
            return f"/{params.get('path', '')}"
        return f"/{name}"


def _init_context(redis):
    cfg = {"features": {"visitor_mgmt": True}, "branding": {}}
    templates_dir = Path(__file__).resolve().parents[1] / "templates"
    gatepass.init_context(cfg, redis, str(templates_dir))


def test_gatepass_view_renders_without_photo():
    r = fakeredis.FakeRedis(decode_responses=True)
    _init_context(r)
    rec = {
        "gate_id": "GP1",
        "ts": 0,
        "name": "A",
        "phone": "1",
        "email": "",
        "host": "H",
        "purpose": "P",
        "status": "approved",
    }
    gatepass._save_gatepass(rec)
    resp = asyncio.run(gatepass.gatepass_view("GP1", DummyRequest()))
    assert resp.status_code == 200


def test_gatepass_view_renders_with_photo():
    r = fakeredis.FakeRedis(decode_responses=True)
    _init_context(r)
    rec = {
        "gate_id": "GP2",
        "ts": 0,
        "name": "A",
        "phone": "1",
        "email": "",
        "host": "H",
        "purpose": "P",
        "status": "approved",
        "image": base64.b64encode(b"img").decode(),
    }
    gatepass._save_gatepass(rec)
    resp = asyncio.run(gatepass.gatepass_view("GP2", DummyRequest()))
    assert resp.status_code == 200
