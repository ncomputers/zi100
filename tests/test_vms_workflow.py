import asyncio
import base64
import json
import types
from pathlib import Path

import fakeredis

from routers import gatepass, visitor


def setup_env(tmp_path):
    cfg = {
        "features": {"visitor_mgmt": True},
        "email": {},
        "base_url": "http://localhost",
        "secret_key": "s",
    }
    r = fakeredis.FakeRedis()
    for name in [
        "gatepass_print.html",
        "gatepass_verify.html",
        "host_verify.html",
        "gatepass_checkout.html",
        "email_invite.html",
        "gatepass_view.html",
    ]:
        (tmp_path / name).write_text("x")
    visitor.init_context(cfg, r, str(tmp_path))
    gatepass.init_context(cfg, r, str(tmp_path))
    return cfg, r


class DummyRequest:
    method = "POST"

    def __init__(self):
        self.session = {"user": {"role": "admin"}}
        self.query_params = {}
        self.base_url = "http://testserver/"


def test_full_workflow(tmp_path):
    cfg, r = setup_env(tmp_path)
    img = "data:image/jpeg;base64," + base64.b64encode(b"img").decode()
    req = DummyRequest()
    invite = asyncio.run(
        visitor.invite_create(
            req,
            name="A",
            phone="1",
            email="",
            visitor_type="Official",
            company="ACME",
            host="H",
            visit_time="2024-01-01 09:00",
            expiry="",
            purpose="P",
            photo=img,
        )
    )
    iid = invite["id"]
    r.hset(f"invite:{iid}", "id_proof_type", "DL")
    result = asyncio.run(visitor.invite_approve(iid, DummyRequest()))
    assert r.hget(f"invite:{iid}", "status") == b"accepted_pending_details"
    gate = asyncio.run(
        visitor.invite_public_submit(
            DummyRequest(),
            iid,
            name="A",
            phone="1",
            email="",
            visitor_type="Official",
            company="ACME",
            host="H",
            visit_time="2024-01-01 10:00",
            purpose_text="Purpose",
            photo=img,
            photo_source="upload",
        )
    )
    gp_id = gate["gate_id"]

    assert r.hget(f"gatepass:pass:{gp_id}", "status") == b"approved"
    asyncio.run(gatepass.gatepass_verify(gp_id, DummyRequest(), host_pass="H"))
    assert r.hget(f"gatepass:pass:{gp_id}", "status") == b"Meeting in progress"
    checkout = asyncio.run(
        gatepass.gatepass_checkout(gp_id, DummyRequest(), host_pass="H")
    )
    assert json.loads(checkout.body)["status"] in {"Completed", "Expired"}
    assert r.hget(f"gatepass:pass:{gp_id}", "status") in {b"Completed", b"Expired"}
