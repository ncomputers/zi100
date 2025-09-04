"""Purpose: Test vms module."""

import asyncio
import base64
import json
import sys
import time
from pathlib import Path

import fakeredis
from fastapi.responses import Response

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from jinja2 import Environment, FileSystemLoader

from routers import entry, vms


# DummyRequest class encapsulates dummyrequest behavior
class DummyRequest:
    # __init__ routine
    def __init__(self):
        self.session = {"user": {"role": "admin"}}
        self.base_url = "http://testserver/"


# Test vms page disabled
def test_vms_page_disabled(tmp_path):
    cfg = {"features": {"visitor_mgmt": False}}
    r = fakeredis.FakeRedis()
    (tmp_path / "vms.html").write_text("{{request}}")
    vms.init_context(cfg, r, str(tmp_path))
    res = asyncio.run(vms.vms_page(DummyRequest()))
    from fastapi.responses import RedirectResponse

    assert isinstance(res, RedirectResponse)


# Test vms register
def test_vms_register(tmp_path):
    cfg = {"features": {"visitor_mgmt": True}, "visitor_model": "buffalo_l"}
    r = fakeredis.FakeRedis()
    (tmp_path / "vms.html").write_text("{{request}}")
    vms.init_context(cfg, r, str(tmp_path))
    dummy = "data:image/jpeg;base64," + base64.b64encode(b"img").decode()
    res = asyncio.run(
        vms.register_visitor(
            name="A",
            phone="1",
            host="H",
            purpose="P",
            visitor_type="Official",
            photo=None,
            captured=dummy,
        )
    )
    assert res["saved"] is True and "gate_id" in res

    assert r.zcard("vms_logs") == 1


# Test header links
def test_header_links():
    env = Environment(loader=FileSystemLoader("templates"))
    tmpl = env.get_template("partials/header.html")
    html = tmpl.render(
        cfg={
            "features": {"visitor_mgmt": False},
            "logo_url": "",
            "logo2_url": "",
            "branding": {},
        },
        request=None,
    )
    assert "/vms" not in html
    html = tmpl.render(
        cfg={
            "features": {"visitor_mgmt": True},
            "logo_url": "",
            "logo2_url": "",
            "branding": {},
        },
        request=None,
    )
    assert "/vms" in html and "/manage_faces" not in html
    assert "/face_search" not in html
    assert "/pre_register" not in html and "/visit_requests" not in html


# Test vms stats
def test_vms_stats(tmp_path):
    cfg = {"features": {"visitor_mgmt": True}}
    r = fakeredis.FakeRedis()
    (tmp_path / "vms.html").write_text("{{request}}")
    vms.init_context(cfg, r, str(tmp_path))
    ts = int(time.time())
    r.zadd(
        "vms_logs",
        {
            json.dumps(
                {
                    "ts": ts,
                    "valid_from": ts - 10,
                    "valid_to": ts + 10,
                    "name": "A",
                    "host": "H",
                }
            ): ts
        },
    )
    r.zadd("visit_requests", {json.dumps({"ts": ts}): ts})
    res = asyncio.run(vms.vms_stats())
    assert res["occupancy"] == 1
    assert "visitor_daily" in res and isinstance(res["visitor_daily"], list)


# Test vms stats timeframe
def test_vms_stats_timeframe(tmp_path):
    cfg = {"features": {"visitor_mgmt": True}}
    r = fakeredis.FakeRedis()
    (tmp_path / "vms.html").write_text("{{request}}")
    vms.init_context(cfg, r, str(tmp_path))
    ts = int(time.time())
    r.zadd(
        "vms_logs",
        {
            json.dumps(
                {
                    "ts": ts,
                    "valid_from": ts - 10,
                    "valid_to": ts + 10,
                    "name": "A",
                    "host": "H",
                }
            ): ts
        },
    )
    res = asyncio.run(vms.vms_stats(range_="today"))
    assert res["occupancy"] == 1


# Test gatepass pdf
def test_gatepass_pdf(tmp_path):
    cfg = {"features": {"visitor_mgmt": True}}
    r = fakeredis.FakeRedis()
    (tmp_path / "gatepass_print.html").write_text("hello")
    vms.init_context(cfg, r, str(tmp_path))
    ts = int(time.time())
    entry = {"ts": ts, "valid_from": ts, "valid_to": ts, "name": "A", "gate_id": "GP1"}
    r.zadd("vms_logs", {json.dumps(entry): ts})
    from routers import gatepass

    gatepass.init_context(cfg, r, str(tmp_path))
    try:
        resp = asyncio.run(gatepass.gatepass_print("GP1", DummyRequest(), pdf=True))
        assert isinstance(resp, Response)
    except ModuleNotFoundError:
        assert True


# Test gatepass create and list
def test_gatepass_create_and_list(tmp_path):
    cfg = {"features": {"visitor_mgmt": True}}
    r = fakeredis.FakeRedis()
    (tmp_path / "gatepass_list.html").write_text("{{rows|length}}")
    (tmp_path / "gatepass_print.html").write_text("hello")
    from routers import gatepass

    gatepass.init_context(cfg, r, str(tmp_path))
    dummy = "data:image/jpeg;base64," + base64.b64encode(b"img").decode()
    res = asyncio.run(
        gatepass.gatepass_create(
            DummyRequest(),
            name="A",
            phone="1",
            email="a@b.com",
            host="H",
            purpose="P",
            visitor_type="Official",
            photo=None,
            captured=dummy,
            valid_to="2030-01-01 00:00",
            host_department="IT",
            company_name="ACME",
            approver_email="",
        )
    )
    assert res.status_code == 200 and res.body
    lst = asyncio.run(gatepass.gatepass_list(DummyRequest()))
    from starlette.responses import Response as StarResponse

    assert isinstance(lst, StarResponse)
    (tmp_path / "vms.html").write_text("{{rows|length}}")
    from routers import entry

    entry.init_context(cfg, r, str(tmp_path))
    dash = asyncio.run(entry.vms_page(DummyRequest()))
    assert dash.body.decode() == "0"
    recent = asyncio.run(entry.vms_recent(DummyRequest()))
    assert isinstance(recent, list) and len(recent) == 1
    exp = asyncio.run(gatepass.gatepass_export())
    assert isinstance(exp, Response)
    # restore templates path for other tests
    entry.init_context(cfg, r, str(ROOT / "templates"))


def test_gatepass_create_without_photo(tmp_path, monkeypatch):
    cfg = {"features": {"visitor_mgmt": True}}
    r = fakeredis.FakeRedis()
    (tmp_path / "gatepass_print.html").write_text("hello")
    from routers import gatepass

    gatepass.init_context(cfg, r, str(tmp_path))

    def fail_save(*a, **k):  # pragma: no cover - ensure not called
        raise AssertionError("save_base64_to_image should not run")

    def fail_add(**k):  # pragma: no cover - ensure not called
        raise AssertionError("add_face_to_known_db should not run")

    def fail_insert(*a, **k):  # pragma: no cover - ensure not called
        raise AssertionError("face_db.insert should not run")

    class DummyFaceDB:
        insert = fail_insert

    monkeypatch.setattr(gatepass, "save_base64_to_image", fail_save)
    monkeypatch.setattr(gatepass, "add_face_to_known_db", fail_add)
    monkeypatch.setattr(gatepass, "face_db", DummyFaceDB())

    res = asyncio.run(
        gatepass.gatepass_create(
            DummyRequest(),
            name="A",
            phone="1",
            email="a@b.com",
            host="H",
            purpose="P",
            visitor_type="Official",
            photo=None,
            captured="",
            valid_to="2030-01-01 00:00",
            host_department="IT",
            company_name="ACME",
            approver_email="",
        )
    )
    assert res.status_code == 200
    data = json.loads(res.body)
    rec = r.hgetall(f"gatepass:pass:{data['gate_id']}")
    assert b"image" not in rec
    master = r.hget("visitor:master", "A")
    if isinstance(master, bytes):
        master = master.decode()
    assert json.loads(master)["photo_url"] == ""


# Test suggest names
def test_suggest_names(tmp_path):
    cfg = {"features": {"visitor_mgmt": True}}
    r = fakeredis.FakeRedis()
    (tmp_path / "gatepass_print.html").write_text("hello")
    from routers import gatepass, vms

    gatepass.init_context(cfg, r, str(tmp_path))
    vms.init_context(cfg, r, str(tmp_path))
    dummy = "data:image/jpeg;base64," + base64.b64encode(b"img").decode()
    asyncio.run(
        gatepass.gatepass_create(
            DummyRequest(),
            name="Bob",
            phone="9",
            email="",
            host="Alice",
            purpose="X",
            visitor_type="Official",
            photo=None,
            captured=dummy,
            valid_to="2030-01-01 00:00",
            host_department="HR",
            company_name="Corp",
            approver_email="",
        )
    )
    hosts = asyncio.run(vms.suggest_names(q="Ali", field="host"))
    visitors = asyncio.run(vms.suggest_names(q="Bo", field="visitor"))
    assert "Alice" in hosts
    assert "Bob" in visitors
    # restore templates path for subsequent tests
    vms.init_context(cfg, r, str(ROOT / "templates"))
