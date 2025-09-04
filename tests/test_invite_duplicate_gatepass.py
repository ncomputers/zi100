import asyncio
import json
from test_invite_gatepass_flow import (
    redis_client,
    mock_public_dir,
    DummyRequest,
    PHOTO_DATA,
)
from routers import visitor

def test_invite_submit_twice_no_duplicate_gatepass(redis_client, mock_public_dir):
    resp = asyncio.run(
        visitor.invite_create(
            DummyRequest(),
            name="Dave",
            phone="555",
            email="",
            visitor_type="Official",
            company="ACME",
            host="Eve",
            visit_time="2024-01-01 10:00",
            expiry="",
            purpose="Discuss",
            photo=PHOTO_DATA,
            send_mail="off",
        )
    )
    iid = resp["id"]
    redis_client.hset(f"invite:{iid}", "id_proof_type", "Passport")
    asyncio.run(visitor.invite_approve(iid))

    gate1 = asyncio.run(
        visitor.invite_public_submit(
            DummyRequest(),
            iid,
            name="Dave",
            phone="555",
            email="",
            visitor_type="Official",
            company="ACME",
            host="Eve",
            visit_time="2024-01-01 10:00",
            purpose_text="Discuss",
            photo=PHOTO_DATA,
            photo_source="upload",
        )
    )
    gate2 = asyncio.run(
        visitor.invite_public_submit(
            DummyRequest(),
            iid,
            name="Dave",
            phone="555",
            email="",
            visitor_type="Official",
            company="ACME",
            host="Eve",
            visit_time="2024-01-01 10:00",
            purpose_text="Discuss",
            photo=PHOTO_DATA,
            photo_source="upload",
        )
    )
    gate_id = gate1.get("gate_id")
    second_id = gate2.get("gate_id", gate_id)
    assert gate_id == second_id
    logs = [json.loads(e) for e in redis_client.zrange("vms_logs", 0, -1)]
    assert sum(1 for l in logs if l.get("invite_id") == iid) == 1
