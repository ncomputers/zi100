import asyncio
import base64
import json
from pathlib import Path

import fakeredis
from fastapi import BackgroundTasks

from modules import gatepass_service
from routers import gatepass


class DummyRequest:
    def __init__(self):
        self.session = {"user": {"role": "admin"}}
        self.base_url = "http://testserver/"

    def url_for(self, name, **params):  # pragma: no cover - simple stub
        return f"/{name}"


def test_gatepass_index_creation_and_lookup(tmp_path):
    cfg = {"features": {"visitor_mgmt": True}, "base_url": "http://localhost"}
    r = fakeredis.FakeRedis()
    (tmp_path / "gatepass_print.html").write_text("x")
    gatepass.init_context(cfg, r, str(tmp_path))
    gatepass_service.init(r)
    dummy = "data:image/jpeg;base64," + base64.b64encode(b"img").decode()

    tasks = BackgroundTasks()
    res = asyncio.run(
        gatepass.gatepass_create(
            DummyRequest(),
            name="A",
            phone="1",
            email="a@b.com",
            host="H",
            purpose="P",
            visitor_type="Official",
            host_department="",
            company_name="C",
            photo=None,
            captured=dummy,
            valid_to="2030-01-01T00:00:00",
            needs_approval="off",
            approver_email="",
            background_tasks=tasks,
        )
    )
    assert res.status_code == 200
    data = json.loads(res.body)
    gate_id = data["gate_id"]

    assert r.hget("gatepass:active_phone", "1").decode() == gate_id
    raw = r.hget("gatepass:active", gate_id)
    assert raw is not None
    obj = json.loads(raw)
    assert obj["gate_id"] == gate_id

    resp = asyncio.run(gatepass.gatepass_active("1"))
    act = json.loads(resp.body)
    assert act["active"] and act["gate_id"] == gate_id

    res2 = asyncio.run(
        gatepass.gatepass_create(
            DummyRequest(),
            name="B",
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
    assert res2.status_code == 400
    assert json.loads(res2.body)["error"] == "active_exists"

    found = gatepass_service._find_gatepass(gate_id)
    assert found and found[0]["gate_id"] == gate_id
