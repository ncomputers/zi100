"""Purpose: Test gatepass workflow module."""

import asyncio
import base64
import json
import sys
from pathlib import Path

import fakeredis
from fastapi import BackgroundTasks, FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.datastructures import URL
from starlette.templating import Jinja2Templates
from starlette.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from modules import email_utils, export, gatepass_service, visitor_db
from routers import gatepass


# DummyRequest class encapsulates dummyrequest behavior
class DummyRequest:
    # __init__ routine
    def __init__(self):
        self.session = {"user": {"role": "admin"}}
        self.base_url = "http://testserver/"

    def url_for(self, name, **params):  # pragma: no cover - simple stub
        base = self.base_url.rstrip("/")
        if name == "gatepass_approve":
            url = URL(f"{base}/gatepass/approve")
        elif name == "gatepass_reject":
            url = URL(f"{base}/gatepass/reject")
        else:
            url = URL(f"{base}/{name}")
        if params:
            return url.include_query_params(**params)
        return url


# Test gatepass approval
def test_gatepass_approval(tmp_path, monkeypatch):
    cfg = {
        "features": {"visitor_mgmt": True},
        "email": {},
        "secret_key": "x",
        "base_url": "http://localhost",
    }
    r = fakeredis.FakeRedis()
    (tmp_path / "gatepass_print.html").write_text("hello")
    (tmp_path / "gatepass_confirm.html").write_text("ok")
    gatepass.init_context(cfg, r, str(tmp_path))
    sent = {}

    # mock_send routine
    def mock_send(subj, msg, recips, cfg2, html=False):
        sent["msg"] = msg
        return True

    monkeypatch.setattr(gatepass, "send_email", mock_send)
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
            needs_approval="on",
            approver_email="boss@a.com",
        )
    )
    assert res.status_code == 200
    data = json.loads(res.body)
    assert "approval_url" in data
    assert "gatepass/approve?token=" in data["approval_url"]
    entries = r.zrange("vms_logs", 0, -1)
    obj = json.loads(entries[0])
    assert obj["status"] == "pending"
    assert "gatepass/approve?token=" in sent["msg"]
    assert "gatepass/reject?token=" in sent["msg"]
    token = (
        f"{obj['gate_id']}:{email_utils.sign_token(obj['gate_id'], cfg['secret_key'])}"
    )
    resp = asyncio.run(gatepass.gatepass_approve(token, DummyRequest()))
    assert resp.status_code == 200
    entries = r.zrange("vms_logs", 0, -1)
    obj = json.loads(entries[0])
    assert obj["status"] == "approved"


def test_welcome_email_with_pdf(tmp_path, monkeypatch):
    cfg = {
        "features": {"visitor_mgmt": True},
        "email": {},
        "base_url": "http://localhost",
    }
    r = fakeredis.FakeRedis()
    (tmp_path / "gatepass_print.html").write_text("{{ card.gate_id }}")
    gatepass.init_context(cfg, r, str(tmp_path))

    monkeypatch.setattr(export, "EXPORT_DIR", tmp_path)

    def fake_export_pdf(html, filename):
        path = export.EXPORT_DIR / f"{filename}.pdf"
        path.write_bytes(b"PDF")
        return path

    monkeypatch.setattr(export, "export_pdf", fake_export_pdf)
    calls = []

    def mock_send(
        subj,
        body,
        recips,
        cfg2,
        html=False,
        attachment=None,
        attachment_name=None,
        attachment_type=None,
    ):
        calls.append(
            {
                "subj": subj,
                "body": body,
                "attachment": attachment,
                "attachment_name": attachment_name,
                "attachment_type": attachment_type,
            }
        )
        return True

    monkeypatch.setattr(gatepass, "send_email", mock_send)
    dummy = "data:image/jpeg;base64," + base64.b64encode(b"img").decode()
    tasks = BackgroundTasks()
    res = asyncio.run(
        gatepass.gatepass_create(
            DummyRequest(),
            name="A",
            phone="1",
            email="x@y.com",
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
            background_tasks=tasks,
        )
    )
    assert res.status_code == 200
    asyncio.run(tasks())
    assert len(calls) == 1
    assert "http://localhost/gatepass/view/" in calls[0]["body"]


def test_approval_links_use_request_base_url(tmp_path, monkeypatch):
    cfg = {"features": {"visitor_mgmt": True}, "email": {}, "secret_key": "s"}
    r = fakeredis.FakeRedis()
    (tmp_path / "gatepass_print.html").write_text("x")
    gatepass.init_context(cfg, r, str(tmp_path))
    captured = {}

    def mock_send(subj, msg, recips, cfg2, html=False):
        captured["msg"] = msg
        return True

    monkeypatch.setattr(gatepass, "send_email", mock_send)
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
            needs_approval="on",
            approver_email="boss@a.com",
        )
    )
    assert res.status_code == 200
    assert "http://testserver/gatepass/approve?token=" in captured["msg"]
    assert "http://testserver/gatepass/reject?token=" in captured["msg"]


def test_welcome_email_uses_request_base_url(tmp_path, monkeypatch):
    cfg = {"features": {"visitor_mgmt": True}, "email": {}}
    r = fakeredis.FakeRedis()
    (tmp_path / "gatepass_print.html").write_text("{{ card.gate_id }}")
    gatepass.init_context(cfg, r, str(tmp_path))
    monkeypatch.setattr(export, "export_pdf", lambda *a, **k: None)
    monkeypatch.setattr(export, "EXPORT_DIR", tmp_path)
    sent = {}

    def mock_send(subj, body, recips, cfg2, html=False, **kwargs):
        sent.setdefault("body", body)
        return True

    monkeypatch.setattr(gatepass, "send_email", mock_send)
    dummy = "data:image/jpeg;base64," + base64.b64encode(b"img").decode()
    tasks = BackgroundTasks()
    res = asyncio.run(
        gatepass.gatepass_create(
            DummyRequest(),
            name="A",
            phone="1",
            email="u@test.com",
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
            background_tasks=tasks,
        )
    )
    data = json.loads(res.body)
    asyncio.run(tasks())
    assert data["digital_pass_url"].startswith("http://testserver/gatepass/view/")
    assert sent["body"].startswith(
        "Welcome! Your gate pass is ready: http://testserver/gatepass/view/"
    )


def test_gatepass_create_with_invite_defaults(tmp_path):
    cfg = {"features": {"visitor_mgmt": True}}
    r = fakeredis.FakeRedis()
    (tmp_path / "gatepass_print.html").write_text("x")
    gatepass.init_context(cfg, r, str(tmp_path))
    invite = {
        "id": "INV1",
        "name": "Invited",
        "phone": "999",
        "email": "i@x.com",
        "host": "Host",
        "purpose": "Meeting",
        "expiry": "2030-01-01T10:00",
    }
    r.hset("invite:INV1", mapping=invite)
    dummy = "data:image/jpeg;base64," + base64.b64encode(b"img").decode()
    res = asyncio.run(
        gatepass.gatepass_create(
            DummyRequest(),
            name="",
            phone="",
            email="",
            host="",
            purpose="",
            visitor_type="Official",
            host_department="",
            company_name="",
            photo=None,
            captured=dummy,
            invite_id="INV1",
            valid_to="",
            needs_approval="off",
            approver_email="",
        )
    )
    assert res.status_code == 200
    entries = r.zrange("vms_logs", 0, -1)
    obj = json.loads(entries[0])
    assert obj["name"] == "Invited"
    assert obj["phone"] == "999"
    assert obj["host"] == "Host"
    assert obj["purpose"] == "Meeting"
    assert obj["invite_id"] == "INV1"


def test_gatepass_create_without_invite_id(tmp_path):
    cfg = {"features": {"visitor_mgmt": True}}
    r = fakeredis.FakeRedis()
    (tmp_path / "gatepass_print.html").write_text("x")
    gatepass.init_context(cfg, r, str(tmp_path))
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
            company_name="",
            photo=None,
            captured=dummy,
            valid_to="",
            needs_approval="off",
            approver_email="",
        )
    )
    assert res.status_code == 200
    entry = json.loads(r.zrange("vms_logs", 0, -1)[0])
    assert entry.get("invite_id") == ""


def test_pdf_generation_error(tmp_path, monkeypatch):
    cfg = {
        "features": {"visitor_mgmt": True},
        "email": {},
        "base_url": "http://localhost",
    }
    r = fakeredis.FakeRedis()
    (tmp_path / "gatepass_print.html").write_text("{{ card.gate_id }}")
    gatepass.init_context(cfg, r, str(tmp_path))
    monkeypatch.setattr(export, "EXPORT_DIR", tmp_path)

    def bad_export_pdf(html, filename):
        raise OSError("boom")

    monkeypatch.setattr(export, "export_pdf", bad_export_pdf)
    calls = []

    def mock_send(
        subj,
        body,
        recips,
        cfg2,
        html=False,
        attachment=None,
        attachment_name=None,
        attachment_type=None,
    ):
        calls.append({"attachment": attachment})
        return True

    monkeypatch.setattr(gatepass, "send_email", mock_send)
    dummy = "data:image/jpeg;base64," + base64.b64encode(b"img").decode()
    tasks = BackgroundTasks()
    res = asyncio.run(
        gatepass.gatepass_create(
            DummyRequest(),
            name="A",
            phone="1",
            email="x@y.com",
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
            background_tasks=tasks,
        )
    )
    data = json.loads(res.body)
    asyncio.run(tasks())
    assert res.status_code == 200
    assert data["saved"] is True
    assert data["digital_pass_url"].startswith("http://localhost/gatepass/view/")
    assert len(calls) == 1
    assert calls[0]["attachment"] is None


def test_duplicate_and_past_date(tmp_path):
    cfg = {"features": {"visitor_mgmt": True}}
    r = fakeredis.FakeRedis()
    (tmp_path / "gatepass_print.html").write_text("hello")
    gatepass.init_context(cfg, r, str(tmp_path))
    future = "2030-01-01 00:00"
    past = "2000-01-01 00:00"
    dummy = "data:image/jpeg;base64," + base64.b64encode(b"img").decode()
    res1 = asyncio.run(
        gatepass.gatepass_create(
            DummyRequest(),
            name="A",
            phone="5",
            email="",
            host="H",
            purpose="P",
            visitor_type="Official",
            host_department="",
            company_name="",
            photo=None,
            captured=dummy,
            valid_to=future,
            needs_approval="off",
            approver_email="",
        )
    )
    assert res1.status_code == 200
    res_dup = asyncio.run(
        gatepass.gatepass_create(
            DummyRequest(),
            name="B",
            phone="5",
            email="",
            host="H",
            purpose="P",
            visitor_type="Official",
            host_department="",
            company_name="",
            photo=None,
            captured=dummy,
            valid_to=future,
            needs_approval="off",
            approver_email="",
        )
    )
    assert res_dup.status_code == 400 and b"active_exists" in res_dup.body
    res_past = asyncio.run(
        gatepass.gatepass_create(
            DummyRequest(),
            name="C",
            phone="6",
            email="",
            host="H",
            purpose="P",
            visitor_type="Official",
            host_department="",
            company_name="",
            photo=None,
            captured=dummy,
            valid_to=past,
            needs_approval="off",
            approver_email="",
        )
    )
    assert res_past.status_code == 400 and b"invalid_date" in res_past.body


def test_gatepass_verify(tmp_path):
    cfg = {"features": {"visitor_mgmt": True}}
    r = fakeredis.FakeRedis()
    (tmp_path / "gatepass_print.html").write_text("x")
    (tmp_path / "gatepass_verify.html").write_text("x")
    gatepass.init_context(cfg, r, str(tmp_path))
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
    resp = asyncio.run(gatepass.gatepass_verify(gp_id, DummyRequest(), host_pass="H"))
    assert resp.status_code == 200
    assert r.hget(f"gatepass:pass:{gp_id}", "status") == b"Meeting in progress"
    entries = r.zrange("vms_logs", 0, -1)
    obj = json.loads(entries[0])
    assert obj["status"] == "Meeting in progress"


def test_gatepass_view(tmp_path):
    cfg = {"features": {"visitor_mgmt": True}}
    r = fakeredis.FakeRedis()
    (tmp_path / "gatepass_print.html").write_text("x")
    (tmp_path / "gatepass_view.html").write_text("x")
    gatepass.init_context(cfg, r, str(tmp_path))
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
    gp_id = json.loads(res.body)["gate_id"]
    resp = asyncio.run(gatepass.gatepass_view(gp_id, DummyRequest()))
    assert resp.status_code == 200


def test_gatepass_sign(tmp_path, monkeypatch):
    cfg = {"features": {"visitor_mgmt": True}}
    r = fakeredis.FakeRedis()
    (tmp_path / "gatepass_print.html").write_text("x")
    gatepass.init_context(cfg, r, str(tmp_path))
    monkeypatch.setattr(gatepass_service, "Path", lambda p: Path(tmp_path) / p)
    monkeypatch.setattr(
        gatepass_service,
        "trim_sorted_set_sync",
        lambda *a, **k: None,
        raising=False,
    )
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
    gp_id = json.loads(res.body)["gate_id"]
    sig = "data:image/png;base64," + base64.b64encode(b"sign").decode()
    resp = asyncio.run(gatepass.gatepass_sign(gp_id, {"image": sig}))
    assert resp.status_code == 200
    path = r.hget(f"gatepass:pass:{gp_id}", "signature").decode()
    assert path == f"/static/signatures/{gp_id}.png"
    entry = json.loads(r.zrange("vms_logs", 0, -1)[0])
    assert entry["signature"] == f"/static/signatures/{gp_id}.png"


def test_signature_render(tmp_path, monkeypatch):
    r = fakeredis.FakeRedis()
    gatepass_service.init(r)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(gatepass_service, "cfg", {"branding": {}})
    css_dir = Path("static/css")
    css_dir.mkdir(parents=True, exist_ok=True)
    (css_dir / "gatepass.css").write_text("/* test css */")
    sig = "data:image/png;base64," + base64.b64encode(b"sign").decode()
    path = gatepass_service.save_signature("GPX", sig)
    assert Path(path.lstrip("/")).exists()
    app = FastAPI()
    static_root = Path(path.lstrip("/")).parents[1]
    app.mount("/static", StaticFiles(directory=static_root), name="static")
    with TestClient(app) as client:
        assert client.get(path).status_code == 200
        assert client.get("/static/css/gatepass.css").status_code == 200
    templates = Jinja2Templates(directory=str(ROOT / "templates"))
    rec = {
        "gate_id": "GPX",
        "name": "A",
        "phone": "1",
        "host": "H",
        "purpose": "P",
        "status": "approved",
        "time": "",
        "image": None,
    }
    html = templates.get_template("gatepass_view.html").render(
        request=DummyRequest(),
        rec=rec,
        cfg={"branding": {}},
        branding={},
        status_color="success",
        signature_url=path,
        qr_link="x",
    )
    assert f'<img src="{path}" class="sig"' in html
    card_html = gatepass_service.render_gatepass_card({**rec, "signature": path})
    assert f"<img src='{path}' class='sig'" in card_html


def test_gatepass_create_no_redis(tmp_path):
    cfg = {"features": {"visitor_mgmt": True}}
    (tmp_path / "gatepass_print.html").write_text("x")
    gatepass.init_context(cfg, None, str(tmp_path))
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
    assert res.status_code == 503 and b"redis_unavailable" in res.body


def test_gatepass_create_init_db_failure(tmp_path, monkeypatch):
    cfg = {"features": {"visitor_mgmt": True}}
    r = fakeredis.FakeRedis()
    (tmp_path / "gatepass_print.html").write_text("x")
    gatepass.init_context(cfg, r, str(tmp_path))

    def bad_init(_):
        raise RuntimeError("no redis")

    monkeypatch.setattr(visitor_db, "init_db", bad_init)
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
    assert res.status_code == 503 and b"redis_unavailable" in res.body


def test_gatepass_create_save_failure(tmp_path, monkeypatch):
    cfg = {"features": {"visitor_mgmt": True}}
    r = fakeredis.FakeRedis()
    (tmp_path / "gatepass_print.html").write_text("x")
    gatepass.init_context(cfg, r, str(tmp_path))

    def fail_save(*args, **kwargs):
        raise RuntimeError("save failed")

    monkeypatch.setattr(gatepass.visitor, "_save_visitor_master", fail_save)
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
    assert res.status_code == 500 and b"visitor_save_failed" in res.body
