import asyncio
import sys
from pathlib import Path

import fakeredis

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from routers import visitor
from config import set_config


class DummyRequest:
    def __init__(self):
        self.session = {"user": {"role": "admin"}}
        self.base_url = "http://testserver/"

    def url_for(self, name, **params):
        return f"/{params.get('path', '')}"


def test_invite_panel_template_renders():
    cfg = {
        "features": {"visitor_mgmt": True},
        "track_objects": [],
        "branding": {},
        "logo_url": "",
    }
    r = fakeredis.FakeRedis()
    set_config(cfg)
    visitor.init_context(cfg, r, str(ROOT / "templates"), [])
    req = DummyRequest()
    resp = asyncio.run(visitor.invites.invite_panel(req))
    assert resp.status_code == 200 and resp.template.name == "invite_panel.html"
    assert "Visitor Type" in resp.body.decode()
