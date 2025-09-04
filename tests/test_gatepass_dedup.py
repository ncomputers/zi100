"""Ensure gatepass updates do not create duplicate log entries."""

import asyncio
import base64
import json
import sys
from pathlib import Path

import fakeredis

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from modules import gatepass_service
from routers import gatepass


class DummyRequest:
    def __init__(self):
        self.session = {"user": {"role": "admin"}}
        self.base_url = "http://testserver/"

    def url_for(self, name, **params):
        return f"/{params.get('path', '')}"


def test_gatepass_log_dedup(tmp_path):
    cfg = {"features": {"visitor_mgmt": True}, "base_url": "http://localhost"}
    r = fakeredis.FakeRedis()
    (tmp_path / "gatepass_print.html").write_text("x")
    gatepass.init_context(cfg, r, str(tmp_path))
    gatepass_service.init(r)

    dummy = "data:image/jpeg;base64," + base64.b64encode(b"img").decode()
    res = asyncio.run(
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
            valid_to="",
            needs_approval="off",
            approver_email="",
        )
    )
    data = json.loads(res.body)
    gp_id = data["gate_id"]

    entries = r.zrange("vms_logs", 0, -1)
    count = sum(1 for e in entries if json.loads(e).get("gate_id") == gp_id)
    assert count == 1

    gatepass_service.update_status(gp_id, "checked_in")
    entries = r.zrange("vms_logs", 0, -1)
    count = sum(1 for e in entries if json.loads(e).get("gate_id") == gp_id)
    assert count == 1
