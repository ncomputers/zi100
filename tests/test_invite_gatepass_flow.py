import asyncio
import base64
import json
import sys
import types
from pathlib import Path

import fakeredis
import pytest
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.testclient import TestClient

sys.modules.setdefault("cv2", types.SimpleNamespace())
from config import set_config
from modules import gatepass_service, visitor_db
from routers import gatepass, visitor


class DummyRequest:
    def __init__(self, query=None):
        self.query_params = query or {}
        self.base_url = "http://test/"

    def url_for(self, name, **params):
        return "/"


@pytest.fixture
def redis_client(tmp_path, monkeypatch):
    r = fakeredis.FakeRedis(decode_responses=True)
    visitor_db.init_db(r)
    gatepass_service.init(r)
    visitor.redis = r
    gatepass.redis = r
    cfg = {
        "features": {"visitor_mgmt": True},
        "base_url": "http://test",
        "branding": {},
        "logo_url": "",
    }
    set_config(cfg)
    visitor.config_obj = cfg
    gatepass.config_obj = cfg
    sys.modules.setdefault(
        "modules.face_db",
        types.SimpleNamespace(
            add_face_if_single_detected=lambda *a, **k: None,
            insert=lambda *a, **k: None,
        ),
    )
    from utils import redis as redis_utils

    for mod in (visitor, __import__("routers.visitor.invites", fromlist=["*"])):
        monkeypatch.setattr(
            mod,
            "trim_sorted_set",
            lambda client, key, ts, retention_secs=None: redis_utils.trim_sorted_set(
                client, key, int(ts), retention_secs
            ),
        )
    monkeypatch.setattr(
        gatepass,
        "save_base64_to_image",
        lambda b64, filename_prefix, subdir: str(tmp_path / "img.jpg"),
    )
    monkeypatch.setattr(gatepass, "add_face_to_known_db", lambda **kwargs: None)
    monkeypatch.setattr(
        gatepass,
        "face_db",
        types.SimpleNamespace(insert=lambda *a, **k: None),
        raising=False,
    )
    return r


@pytest.fixture
def mock_public_dir(tmp_path, monkeypatch):
    from pathlib import Path as RealPath

    def _mock_path(p):
        if p == "public":
            return tmp_path
        return RealPath(p)

    monkeypatch.setattr(visitor, "Path", _mock_path)
    return tmp_path


SAMPLE_B64 = base64.b64encode(b"img").decode()
PHOTO_DATA = f"data:image/jpeg;base64,{SAMPLE_B64}"


def test_manual_invite_creation(redis_client, mock_public_dir):
    resp = asyncio.run(
        visitor.invite_create(
            DummyRequest(),
            name="Alice",
            phone="123",
            email="",
            visitor_type="Official",
            company="ACME",
            host="Bob",
            visit_time="2024-01-01 09:00",
            expiry="",
            purpose="Meet",
            photo=PHOTO_DATA,
            send_mail="off",
        )
    )
    iid = resp["id"]
    assert (mock_public_dir / "invite_photos" / f"{iid}.jpg").exists()
    rec = redis_client.hgetall(f"invite:{iid}")
    assert rec["status"] == "created"
    assert rec["photo_url"] == f"/invite_photos/{iid}.jpg"
    assert rec["visitor_type"] == "Official"
    assert rec["company"] == "ACME"


def test_public_invite_form_submission_with_photo(redis_client, mock_public_dir):
    resp = asyncio.run(
        visitor.invite_create(
            DummyRequest(query={"link": "1"}),
            name="",
            phone="",
            email="",
            visitor_type="Official",
            company="ACME",
            host="Host",
            visit_time="",
            expiry="",
            purpose="",
            photo="",
            send_mail="off",
        )
    )
    iid = resp["link"].split("id=")[-1]
    asyncio.run(
        visitor.invite_public_submit(
            DummyRequest(),
            iid,
            name="Charlie",
            phone="999",
            email="c@example.com",
            visitor_type="Official",
            company="ACME",
            host="Host",
            visit_time="2024-01-01 10:00",
            purpose_text="Meet",
            photo=PHOTO_DATA,
            photo_source="upload",
        )
    )
    rec = redis_client.hgetall(f"invite:{iid}")
    assert rec["name"] == "Charlie"
    assert rec["status"] == "pending"
    assert rec["photo_url"] == f"/invite_photos/{iid}.jpg"
    assert rec["visitor_type"] == "Official"
    assert rec["company"] == "ACME"


def test_invite_approval_requires_details_before_gatepass(
    redis_client, mock_public_dir
):
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
    redis_client.hset(f"invite:{iid}", "id_proof_type", "DL")
    result = asyncio.run(visitor.invite_approve(iid))
    assert "details_url" in result
    assert redis_client.zrange("vms_logs", 0, -1) == []
    gate = asyncio.run(
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
    gate_id = gate["gate_id"]

    log = json.loads(redis_client.zrange("vms_logs", 0, -1)[0])
    assert log["gate_id"] == gate_id
    assert log["invite_id"] == iid
    assert log["name"] == "Dave"
    assert log["image"]
    assert log["visitor_type"] == "Official"
    assert log["company_name"] == "ACME"


def test_public_invite_submission_approval_creates_gatepass(
    redis_client, mock_public_dir
):
    resp = asyncio.run(
        visitor.invite_create(
            DummyRequest(query={"link": "1"}),
            name="",
            phone="",
            email="",
            visitor_type="Official",
            company="ACME",
            host="Host",
            visit_time="",
            expiry="",
            purpose="",
            photo="",
            send_mail="off",
        )
    )
    iid = resp["link"].split("id=")[-1]
    asyncio.run(
        visitor.invite_public_submit(
            DummyRequest(),
            iid,
            name="Zed",
            phone="333",
            email="z@example.com",
            visitor_type="Official",
            company="ACME",
            host="Host",
            visit_time="2024-01-02 11:00",
            purpose_text="Review",
            photo=PHOTO_DATA,
            photo_source="upload",
        )
    )
    asyncio.run(visitor.invite_approve(iid))
    complete = asyncio.run(
        visitor.invite_complete_submit(
            iid,
            government_id="ID2",
            phone="333",
            purpose="Review",
            vehicle="",
            photo=PHOTO_DATA,
        )
    )
    redis_client.hset(f"invite:{iid}", "id_proof_type", "Passport")
    result = asyncio.run(visitor.invite_approve(iid))
    assert "details_url" in result
    gate = asyncio.run(
        visitor.invite_public_submit(
            DummyRequest(),
            iid,
            name="Zed",
            phone="333",
            email="z@example.com",
            visitor_type="Official",
            company="ACME",
            host="Host",
            visit_time="2024-01-02 11:00",
            purpose_text="Review",
            photo=PHOTO_DATA,
            photo_source="upload",
        )
    )
    gate_id = gate["gate_id"]

    logs = [json.loads(e) for e in redis_client.zrange("vms_logs", 0, -1)]
    assert any(l.get("gate_id") == gate_id for l in logs)
    log = next(l for l in logs if l.get("gate_id") == gate_id)
    assert log["invite_id"] == iid
    assert log["name"] == "Zed"
    assert log["company_name"] == "ACME"


def test_invite_approval_missing_required_data(redis_client, mock_public_dir):
    resp = asyncio.run(
        visitor.invite_create(
            DummyRequest(),
            name="NoID",
            phone="1234",
            email="",
            visitor_type="Official",
            company="ACME",
            host="Host",
            visit_time="2024-01-01 10:00",
            expiry="",
            purpose="Visit",
            photo=PHOTO_DATA,
            send_mail="off",
        )
    )
    iid = resp["id"]
    result = asyncio.run(visitor.invite_approve(iid))
    assert result["error"] == "missing_fields"
    assert "id_proof_type" in result["fields"]
    assert not redis_client.zrange("vms_logs", 0, -1)


def test_invite_form_route(redis_client, mock_public_dir):
    visitor.templates = Jinja2Templates("templates")
    app = FastAPI()
    app.mount("/static", StaticFiles(directory="static"), name="static")
    app.include_router(visitor.router)
    resp = asyncio.run(
        visitor.invite_create(
            DummyRequest(query={"link": "1"}),
            name="",
            phone="",
            email="",
            visitor_type="Official",
            company="ACME",
            host="Host",
            visit_time="",
            expiry="",
            purpose="",
            photo="",
            send_mail="off",
        )
    )
    invite_id = resp["link"].split("id=")[-1]
    client = TestClient(app)
    r = client.get(f"/invite/form?id={invite_id}")
    assert r.status_code == 200
    assert "Visitor Invite Form" in r.text
