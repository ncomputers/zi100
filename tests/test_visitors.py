"""Purpose: Test visitors module."""

import asyncio
import json
import sys
import time
from datetime import datetime
from pathlib import Path

import fakeredis
import numpy as np
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import types

sys.modules.setdefault("google", types.SimpleNamespace())
sys.modules.setdefault(
    "google.auth",
    types.SimpleNamespace(
        transport=types.SimpleNamespace(requests=types.SimpleNamespace(Request=object))
    ),
)
sys.modules.setdefault(
    "google.auth.transport",
    types.SimpleNamespace(requests=types.SimpleNamespace(Request=object)),
)
sys.modules.setdefault(
    "google.auth.transport.requests", types.SimpleNamespace(Request=object)
)
sys.modules.setdefault(
    "google.oauth2",
    types.SimpleNamespace(credentials=types.SimpleNamespace(Credentials=object)),
)
sys.modules.setdefault(
    "google.oauth2.credentials", types.SimpleNamespace(Credentials=object)
)
sys.modules.setdefault(
    "google_auth_oauthlib",
    types.SimpleNamespace(flow=types.SimpleNamespace(InstalledAppFlow=object)),
)
sys.modules.setdefault(
    "google_auth_oauthlib.flow", types.SimpleNamespace(InstalledAppFlow=object)
)

from fastapi import HTTPException

from routers import visitor
from routers.visitor import registration


# DummyRequest class encapsulates dummyrequest behavior
class DummyRequest:
    # __init__ routine
    def __init__(self):
        self.session = {"user": {"role": "admin"}}


# Test api requires feature
def test_api_requires_feature(tmp_path):
    cfg = {"features": {"visitor_mgmt": False}, "visitor_model": "buffalo_l"}
    r = fakeredis.FakeRedis()
    visitor.init_context(cfg, r, str(tmp_path), [])
    from fastapi.responses import JSONResponse

    res = asyncio.run(registration.api_visitor_report(include_pending=False))
    assert isinstance(res, JSONResponse)
    assert res.status_code == 403


def test_api_visitor_report_filters(tmp_path):
    cfg = {"features": {"visitor_mgmt": True}, "visitor_model": "buffalo_l"}
    r = fakeredis.FakeRedis()
    visitor.init_context(cfg, r, str(tmp_path), [])

    # create sample visitor log entries
    def ts(s: str) -> int:
        return int(datetime.strptime(s, "%Y-%m-%d %H:%M:%S").timestamp())

    approved = {
        "gate_id": "GP1",
        "name": "A",
        "phone": "1",
        "host": "H",
        "visitor_type": "Official",
        "purpose": "P",
        "status": "approved",
        "ts": ts("1970-01-01 00:16:00"),
    }
    pending = {
        "gate_id": "GP2",
        "name": "B",
        "phone": "2",
        "host": "H",
        "visitor_type": "Official",
        "purpose": "Q",
        "status": "pending",
        "ts": ts("1970-01-01 00:18:20"),
    }
    other = {
        "gate_id": "GP3",
        "name": "C",
        "phone": "3",
        "host": "H",
        "visitor_type": "Personal",
        "purpose": "R",
        "status": "approved",
        "ts": ts("1970-01-01 01:00:00"),
    }
    r.zadd("vms_logs", {json.dumps(approved): approved["ts"]})
    r.zadd("vms_logs", {json.dumps(pending): pending["ts"]})
    r.zadd("vms_logs", {json.dumps(other): other["ts"]})
    start = "1970-01-01"
    end = "1970-01-01"
    data = asyncio.run(
        registration.api_visitor_report(
            start_date=start,
            end_date=end,
            vtype="Official",
            include_pending=False,
        )
    )
    assert len(data["items"]) == 1
    rec = data["items"][0]

    assert rec["gate_id"] == "GP1"
    assert rec["time"] == "1970-01-01 00:16"
    data2 = asyncio.run(
        registration.api_visitor_report(
            start_date=start, end_date=end, vtype="Official", include_pending=True
        )
    )
    assert len(data2["items"]) == 2


def test_api_visitor_report_additional_statuses(tmp_path):
    cfg = {"features": {"visitor_mgmt": True}, "visitor_model": "buffalo_l"}
    r = fakeredis.FakeRedis()
    visitor.init_context(cfg, r, str(tmp_path), [])
    base = {
        "name": "A",
        "phone": "1",
        "host": "H",
        "visitor_type": "Official",
        "purpose": "P",
        "ts": int(datetime(1970, 1, 1).timestamp()),
    }
    statuses = {
        "GP1": "Meeting in progress",
        "GP2": "Completed",
        "GP3": "Expired",
        "GP4": "rejected",
        "GP5": "cancelled",
    }
    for gid, status in statuses.items():
        entry = base | {"gate_id": gid, "status": status, "ts": base["ts"]}
        r.zadd("vms_logs", {json.dumps(entry): entry["ts"]})
    start = "1970-01-01"
    end = "1970-01-02"
    data = asyncio.run(
        registration.api_visitor_report(
            start_date=start,
            end_date=end,
            vtype="Official",
            include_pending=False,
        )
    )
    gids = {rec["gate_id"] for rec in data["items"]}

    assert {"GP1", "GP2", "GP3"} <= gids
    assert "GP4" not in gids
    assert "GP5" not in gids


# Verify ts field handling
def test_api_visitor_report_ts_field(tmp_path):
    cfg = {"features": {"visitor_mgmt": True}, "visitor_model": "buffalo_l"}
    r = fakeredis.FakeRedis()
    visitor.init_context(cfg, r, str(tmp_path), [])
    epoch = 1609459200  # 2021-01-01 00:00:00
    base = {
        "name": "A",
        "phone": "1",
        "host": "H",
        "visitor_type": "Official",
        "purpose": "P",
        "status": "approved",
    }
    r.zadd(
        "vms_logs",
        {json.dumps(base | {"gate_id": "GP1", "ts": epoch}): epoch},
    )
    r.zadd(
        "vms_logs",
        {json.dumps(base | {"gate_id": "GP2", "ts": str(epoch + 60)}): epoch + 60},
    )
    start = "2021-01-01"
    end = "2021-01-01"
    data = asyncio.run(
        registration.api_visitor_report(
            start_date=start,
            end_date=end,
            vtype="Official",
            include_pending=False,
        )
    )
    assert len(data["items"]) == 2
    times = {rec["gate_id"]: rec["time"] for rec in data["items"]}

    assert times["GP1"] == "2021-01-01 00:00"
    assert times["GP2"] == "2021-01-01 00:01"


def test_api_visitor_report_pagination(monkeypatch):
    records = [
        {
            "gate_id": "GP0",
            "name": "A",
            "phone": "1",
            "host": "H",
            "visitor_type": "Official",
            "purpose": "P",
            "time": "t",
        },
        {
            "gate_id": "GP1",
            "name": "B",
            "phone": "2",
            "host": "H",
            "visitor_type": "Official",
            "purpose": "P",
            "time": "t",
        },
        {
            "gate_id": "GP2",
            "name": "C",
            "phone": "3",
            "host": "H",
            "visitor_type": "Official",
            "purpose": "P",
            "time": "t",
        },
    ]

    async def fake_fetch(*args, **kwargs):
        return records

    monkeypatch.setattr(registration, "_fetch_visitors", fake_fetch)
    data1 = asyncio.run(
        registration.api_visitor_report(page=1, page_size=2, include_pending=False)
    )
    assert len(data1["items"]) == 2
    assert data1["total"] == 3
    data2 = asyncio.run(
        registration.api_visitor_report(page=2, page_size=2, include_pending=False)
    )
    assert len(data2["items"]) == 1


def test_api_visitor_report_view_grouping(monkeypatch):
    records = [
        {
            "gate_id": "GP1",
            "name": "A",
            "phone": "1",
            "host": "H1",
            "visitor_type": "Official",
            "purpose": "P",
            "time": "t",
        },
        {
            "gate_id": "GP2",
            "name": "A",
            "phone": "1",
            "host": "H2",
            "visitor_type": "Official",
            "purpose": "P",
            "time": "t",
        },
        {
            "gate_id": "GP3",
            "name": "B",
            "phone": "2",
            "host": "H1",
            "visitor_type": "Official",
            "purpose": "P",
            "time": "t",
        },
    ]

    async def fake_fetch(*args, **kwargs):
        return records

    monkeypatch.setattr(registration, "_fetch_visitors", fake_fetch)
    visitor_view = asyncio.run(
        registration.api_visitor_report(view="visitor", include_pending=False)
    )
    counts = {item["name"]: item["visits"] for item in visitor_view["items"]}
    assert counts["A"] == 2
    assert counts["B"] == 1
    host_view = asyncio.run(
        registration.api_visitor_report(view="host", include_pending=False)
    )
    mapping = {item["host"]: item["visitors"] for item in host_view["items"]}
    assert mapping["H1"] == 2
    assert mapping["H2"] == 1


def test_api_visitor_report_span_validation(tmp_path):
    cfg = {"features": {"visitor_mgmt": True}, "visitor_model": "buffalo_l"}
    r = fakeredis.FakeRedis()
    visitor.init_context(cfg, r, str(tmp_path), [])
    start = "1970-01-01"
    end = "1970-04-05"  # > 90 days apart
    with pytest.raises(HTTPException):
        asyncio.run(
            registration.api_visitor_report(
                start_date=start, end_date=end, include_pending=False
            )
        )


# Test invite flow
def test_invite_flow(tmp_path):
    cfg = {
        "features": {"visitor_mgmt": True},
        "visitor_model": "buffalo_l",
        "email": {},
    }
    r = fakeredis.FakeRedis()
    (tmp_path / "invite_panel.html").write_text("{{request}}")
    (tmp_path / "invite_public.html").write_text("{{invite_id}}")
    visitor.init_context(cfg, r, str(tmp_path), [])
    app = FastAPI()
    app.post("/invite/create")(visitor.invite_create)
    app.get("/invite/list")(visitor.invite_list)
    app.get("/invite/lookup")(visitor.invite_lookup)
    app.get("/invite/{iid}")(visitor.invite_get)
    client = TestClient(app)
    r.hset("host_master", "H", json.dumps({"email": ""}))
    resp = client.post(
        "/invite/create",
        data={
            "name": "A",
            "phone": "1234567890",
            "visitor_type": "Official",
            "company": "ACME",
            "host": "H",
            "visit_time": "2025-01-01T10:00",
        },
    )
    assert resp.status_code == 200
    iid = resp.json()["id"]
    assert r.zcard("invite_ids") == 1
    data = client.get("/invite/list").json()
    assert data[0]["name"] == "A"
    assert data[0]["visitor_type"] == "Official"
    assert data[0]["company"] == "ACME"
    info = client.get("/invite/lookup", params={"phone": "1234567890"}).json()
    assert info["name"] == "A"
    detail = client.get(f"/invite/{iid}").json()
    assert detail["name"] == "A"
    assert detail["visitor_type"] == "Official"
    assert detail["company"] == "ACME"


# Test face search
def test_face_search(tmp_path):
    cfg = {"features": {"visitor_mgmt": True}, "visitor_model": "buffalo_l"}
    r = fakeredis.FakeRedis()
    (tmp_path / "face_search.html").write_text("{{results}}")
    visitor.init_context(cfg, r, str(tmp_path), [])
    rid = "id1"
    r.hset(
        f"face:known:{rid}",
        mapping={"name": "A", "embedding": json.dumps([0.1, 0.1]), "image_path": ""},
    )
    r.sadd("face:known_ids", rid)

    # Face class encapsulates face behavior
    class Face:
        embedding = np.array([0.1, 0.1], dtype=np.float32)

    # App class encapsulates app behavior
    class App:
        # get routine
        def get(self, img):
            return [Face]

    visitor.face_app = App()
    req = DummyRequest()
    resp = asyncio.run(visitor.face_search_form(req))
    from fastapi.responses import HTMLResponse

    assert isinstance(resp, HTMLResponse)
    resp2 = asyncio.run(
        visitor.face_search(
            req, photo=None, captured="data:image/jpeg;base64,a", top_n=1
        )
    )
    assert isinstance(resp2, HTMLResponse)


# Test invite and custom report
def test_invite_and_custom_report(tmp_path):
    cfg = {
        "features": {"visitor_mgmt": True},
        "visitor_model": "buffalo_l",
        "email": {},
    }
    r = fakeredis.FakeRedis()
    (tmp_path / "invite_public.html").write_text("{{invite_id}}")
    visitor.init_context(cfg, r, str(tmp_path), [])
    app = FastAPI()
    app.post("/invite/create")(visitor.invite_create)
    app.get("/invite/list")(visitor.invite_list)
    app.put("/invite/approve/{iid}")(visitor.invite_approve)
    client = TestClient(app)
    client.post(
        "/invite/create",
        data={
            "name": "A",
            "phone": "1",
            "visitor_type": "Official",
            "company": "ACME",
            "host": "H",
            "visit_time": "2025-01-01T10:00",
        },
    )
    iid = r.zrevrange("invite_ids", 0, -1)[0].decode()
    client.put(f"/invite/approve/{iid}")
    r.zadd("vms_logs", {json.dumps({"ts": 1, "name": "A", "host": "H"}): 1})
    stats = asyncio.run(visitor.custom_report())
    assert stats["rows"]


# Test visitor suggestion API
def test_visitor_suggest(tmp_path):
    cfg = {"features": {"visitor_mgmt": True}, "visitor_model": "buffalo_l"}
    r = fakeredis.FakeRedis()
    visitor.init_context(cfg, r, str(tmp_path), [])
    entry = {
        "ts": 1,
        "name": "Alice",
        "phone": "123",
        "visitor_type": "Official",
        "company_name": "ACME",
    }
    r.zadd("vms_logs", {json.dumps(entry): entry["ts"]})
    app = FastAPI()
    app.get("/vms/visitor/suggest")(visitor.visitor_suggest)
    client = TestClient(app)
    resp = client.get("/vms/visitor/suggest", params={"name_prefix": "Al"})
    assert resp.status_code == 200
    assert {
        "name": "Alice",
        "phone": "123",
        "visitor_type": "Official",
        "company": "ACME",
        "photo_url": "",
    } in resp.json()


def test_host_cache_uses_redis(tmp_path):
    cfg = {"features": {"visitor_mgmt": True}, "visitor_model": "buffalo_l"}
    r = fakeredis.FakeRedis()
    visitor.init_context(cfg, r, str(tmp_path), [])
    r.hset("host_master", mapping={"H1": json.dumps({"email": ""})})
    names1 = visitor.get_host_names_cached()
    assert names1 == ["H1"]
    assert r.ttl("host_cache") > 0
    r.hset("host_master", mapping={"H2": json.dumps({"email": ""})})
    names2 = visitor.get_host_names_cached()
    assert names2 == ["H1"]
    visitor.invalidate_host_cache()
    names3 = visitor.get_host_names_cached()
    assert {"H1", "H2"} == set(names3)


@pytest.mark.xfail(reason="export endpoint requires Query defaults fix")
def test_export_visitors_endpoint(tmp_path):
    cfg = {"features": {"visitor_mgmt": True}, "visitor_model": "buffalo_l"}
    r = fakeredis.FakeRedis()
    visitor.init_context(cfg, r, str(tmp_path), [])
    entry = {
        "gate_id": "GPX",
        "name": "John",
        "phone": "1",
        "host": "Host",
        "visitor_type": "Official",
        "purpose": "P",
        "status": "approved",
        "ts": int(time.time()),
    }
    r.zadd("vms_logs", {json.dumps(entry): entry["ts"]})
    app = FastAPI()
    app.include_router(registration.router)
    client = TestClient(app)
    res = client.get(
        "/visitors/export",
        params={
            "from": "1970-01-01T00:00:00Z",
            "to": "1970-01-02T00:00:00Z",
            "type": "Official",
        },
    )
    assert res.status_code == 200
    assert "text/csv" in res.headers.get("content-type", "")
    assert entry["gate_id"] in res.text
