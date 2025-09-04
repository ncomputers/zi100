"""Purpose: Test reports module."""

# test_reports.py
import asyncio
import json
import sys
import time
from datetime import datetime
from pathlib import Path

import fakeredis
import pytest
from fastapi import FastAPI
from fastapi.templating import Jinja2Templates
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.modules.setdefault("cv2", type("cv2", (), {}))
sys.modules.setdefault(
    "torch",
    type("torch", (), {"cuda": type("cuda", (), {"is_available": lambda: False})}),
)
sys.modules.setdefault("ultralytics", type("ultralytics", (), {"YOLO": object}))
sys.modules.setdefault("deep_sort_realtime", type("ds", (), {}))
sys.modules["deep_sort_realtime.deepsort_tracker"] = type("t", (), {"DeepSort": object})
sys.modules.setdefault("imagehash", type("imagehash", (), {}))

from routers import ppe_reports, reports
from schemas.ppe_report import PPEReportQuery
from schemas.report import ReportQuery


# DummyRequest class encapsulates dummyrequest behavior
class DummyRequest:
    # __init__ routine
    def __init__(self):
        self.session = {"user": {"role": "admin"}}

    def url_for(self, name: str, **path_params):
        if name == "static":
            return f"/static/{path_params.get('path', '')}"
        return "/"


@pytest.fixture
# redis_client routine
def redis_client():
    return fakeredis.FakeRedis()


@pytest.fixture
# cfg routine
def cfg():
    return {
        "track_objects": ["person"],
        "helmet_conf_thresh": 0.5,
        "track_ppe": ["helmet"],
        "branding": {},
        "logo_url": "",
        "features": {"visitor_mgmt": False},
    }


@pytest.fixture(autouse=True)
# setup_context routine
def setup_context(redis_client, cfg, tmp_path):
    reports.init_context(cfg, {}, redis_client, str(tmp_path), [])
    ppe_reports.init_context(cfg, {}, redis_client, str(tmp_path))


@pytest.fixture
def client(monkeypatch):
    app = FastAPI()
    app.include_router(reports.router)
    monkeypatch.setattr(reports, "require_roles", lambda request, roles: True)
    return TestClient(app)


# Test report page no data message
def test_report_page_no_data(redis_client, cfg):
    import config as config_mod

    config_mod.set_config(cfg)
    reports.init_context(
        config_mod.config, {}, redis_client, str(ROOT / "templates"), []
    )
    req = DummyRequest()
    resp = asyncio.run(reports.report_page(req))
    assert b"No report data available" in resp.body


# Test ppe report page no data message
def test_ppe_report_page_no_data(redis_client, cfg):
    import config as config_mod

    config_mod.set_config(cfg)
    ppe_reports.init_context(
        config_mod.config, {}, redis_client, str(ROOT / "templates")
    )
    req = DummyRequest()
    resp = asyncio.run(ppe_reports.ppe_report_page(req, ""))
    assert b"No PPE report data available" in resp.body


# Test report data graph
def test_report_data_graph(redis_client):
    now = int(time.time() // 60 * 60)
    entry1 = {"ts": now - 120, "in_person": 1, "out_person": 0}
    entry2 = {"ts": now - 60, "in_person": 2, "out_person": 1}
    redis_client.zadd("history", {json.dumps(entry1): entry1["ts"]})
    redis_client.zadd("history", {json.dumps(entry2): entry2["ts"]})
    start = datetime.fromtimestamp(now - 180).isoformat()
    end = datetime.fromtimestamp(now).isoformat()
    query = ReportQuery(start=start, end=end, type="person", view="graph", rows=50)
    res = asyncio.run(reports._report_data(query))
    assert res["ins"] == [1, 1]
    assert res["outs"] == [0, 1]
    assert res["current"] == [1, 1]


# Test table view rows and ordering


def test_report_table_rows(redis_client, client):
    now = int(time.time() // 60 * 60)
    entry1 = {
        "ts": now - 60,
        "cam_id": 1,
        "track_id": 1,
        "direction": "in",
        "label": "person",
        "path": "a.jpg",
    }
    entry2 = {
        "ts": now - 30,
        "cam_id": 2,
        "track_id": 2,
        "direction": "out",
        "label": "person",
        "path": "b.jpg",
    }
    redis_client.zadd("person_logs", {json.dumps(entry1): entry1["ts"]})
    redis_client.zadd("person_logs", {json.dumps(entry2): entry2["ts"]})
    start = datetime.fromtimestamp(now - 120).strftime("%Y-%m-%d %H:%M")
    end = datetime.fromtimestamp(now).strftime("%Y-%m-%d %H:%M")
    params = {
        "start": start,
        "end": end,
        "type": "person",
        "view": "table",
        "rows": 10,
        "cam_id": "",
        "label": "",
        "cursor": 0,
    }
    res = client.get("/report_data", params=params)
    assert res.status_code == 200
    data = res.json()
    assert len(data["rows"]) == 2
    assert data["rows"][0]["cam_id"] == 2


# Test cam_id and label filters
def test_report_filters(redis_client, client):
    now = int(time.time() // 60 * 60)
    entries = [
        {"ts": now - 30, "cam_id": 1, "track_id": 1, "label": "foo"},
        {"ts": now - 20, "cam_id": 2, "track_id": 2, "label": "bar"},
    ]
    for e in entries:
        redis_client.zadd("person_logs", {json.dumps(e): e["ts"]})
    start = datetime.fromtimestamp(now - 60).strftime("%Y-%m-%d %H:%M")
    end = datetime.fromtimestamp(now).strftime("%Y-%m-%d %H:%M")
    params_cam = {
        "start": start,
        "end": end,
        "type": "person",
        "view": "table",
        "rows": 10,
        "cam_id": 1,
        "label": "",
        "cursor": 0,
    }
    res_cam = client.get("/report_data", params=params_cam).json()
    assert len(res_cam["rows"]) == 1
    assert res_cam["rows"][0]["cam_id"] == 1
    params_label = {
        "start": start,
        "end": end,
        "type": "person",
        "view": "table",
        "rows": 10,
        "cam_id": "",
        "label": "bar",
        "cursor": 0,
    }
    res_label = client.get("/report_data", params=params_label).json()
    assert len(res_label["rows"]) == 1
    assert res_label["rows"][0]["label"] == "bar"


# Test pagination via cursor
def test_report_pagination(redis_client, client):
    now = int(time.time() // 60 * 60)
    for i in range(3):
        entry = {"ts": now - i * 10, "cam_id": 1, "track_id": i, "label": "person"}
        redis_client.zadd("person_logs", {json.dumps(entry): entry["ts"]})
    start = datetime.fromtimestamp(now - 40).strftime("%Y-%m-%d %H:%M")
    end = datetime.fromtimestamp(now).strftime("%Y-%m-%d %H:%M")
    params1 = {
        "start": start,
        "end": end,
        "type": "person",
        "view": "table",
        "rows": 2,
        "cam_id": "",
        "label": "",
        "cursor": 0,
    }
    res1 = client.get("/report_data", params=params1).json()
    assert len(res1["rows"]) == 2
    assert res1["next_cursor"] == 2
    params2 = params1.copy()
    params2["cursor"] = res1["next_cursor"]
    res2 = client.get("/report_data", params=params2).json()
    assert len(res2["rows"]) == 1
    assert res2["next_cursor"] is None


# Test report data cache
@pytest.mark.xfail(reason="report caching pending update")
def test_report_data_cache(redis_client):
    now = int(time.time())
    entry1 = {"ts": now - 60, "in_person": 1, "out_person": 0}
    redis_client.zadd("history", {json.dumps(entry1): entry1["ts"]})
    start = datetime.fromtimestamp(now - 120).isoformat()
    end = datetime.fromtimestamp(now).isoformat()
    query = ReportQuery(start=start, end=end, type="person", view="graph", rows=50)
    res1 = asyncio.run(reports.report_data(query, DummyRequest()))
    entry2 = {"ts": now - 30, "in_person": 5, "out_person": 0}
    redis_client.zadd("history", {json.dumps(entry2): entry2["ts"]})
    res2 = asyncio.run(reports.report_data(query, DummyRequest()))
    assert res2 == res1
    cache_key = f"report_data:{start}:{end}:person:graph:50"
    ttl = redis_client.ttl(cache_key)
    assert 0 < ttl <= 300


# Test ppe report data
def test_ppe_report_data(redis_client, cfg):
    now = int(time.time())
    entry = {
        "ts": now - 30,
        "cam_id": 1,
        "track_id": 2,
        "status": "no_helmet",
        "conf": 0.9,
        "color": None,
        "path": "snap.jpg",
    }
    redis_client.zadd("ppe_logs", {json.dumps(entry): entry["ts"]})
    start = datetime.fromtimestamp(now - 60).isoformat()
    end = datetime.fromtimestamp(now).isoformat()
    query = PPEReportQuery(
        start=start, end=end, status=["no_helmet"], min_conf=None, color=None
    )
    res = asyncio.run(ppe_reports.ppe_report_data(query))
    assert len(res["rows"]) == 1
    assert res["rows"][0]["status"] == "no_helmet"


# Test ppe report caching and invalidation
def test_ppe_report_cache(redis_client):
    now = int(time.time())
    entry1 = {
        "ts": now - 60,
        "cam_id": 1,
        "track_id": 2,
        "status": "no_helmet",
        "conf": 0.9,
        "color": None,
        "path": "snap.jpg",
    }
    redis_client.zadd("ppe_logs", {json.dumps(entry1): entry1["ts"]})
    start = datetime.fromtimestamp(now - 120).isoformat()
    end = datetime.fromtimestamp(now).isoformat()
    query = PPEReportQuery(
        start=start, end=end, status=["no_helmet"], min_conf=None, color=None
    )
    res1 = asyncio.run(ppe_reports.ppe_report_data(query))
    entry2 = {
        "ts": now - 30,
        "cam_id": 1,
        "track_id": 3,
        "status": "no_helmet",
        "conf": 0.95,
        "color": None,
        "path": "snap2.jpg",
    }
    redis_client.zadd("ppe_logs", {json.dumps(entry2): entry2["ts"]})
    res2 = asyncio.run(ppe_reports.ppe_report_data(query))
    assert res2 == res1
    ver = int(redis_client.get("ppe_report_version") or 0)
    cache_key = f"ppe_report:{start}:{end}:no_helmet:None:None:{ver}"
    ttl = redis_client.ttl(cache_key)
    assert 0 < ttl <= 300
    redis_client.incr("ppe_report_version")
    res3 = asyncio.run(ppe_reports.ppe_report_data(query))
    assert len(res3["rows"]) == 2


# Test status options no duplicates
def test_status_options_no_duplicates(redis_client, cfg, tmp_path):
    req = DummyRequest()
    (tmp_path / "ppe_report.html").write_text("")
    templates = Jinja2Templates(directory=str(tmp_path))
    ppe_reports.templates = templates
    res = asyncio.run(ppe_reports.ppe_report_page(req, ""))
    opts = res.context["status_options"]
    assert opts == ["helmet", "no_helmet", "misc"]
    assert len(opts) == len(set(opts))


# Test vehicle report plate included
def test_vehicle_report_plate_included(redis_client, tmp_path):
    cfg2 = {
        "track_objects": ["person", "vehicle", "number_plate"],
        "helmet_conf_thresh": 0.5,
        "track_ppe": ["helmet"],
    }
    reports.init_context(cfg2, {}, redis_client, str(tmp_path), [])
    now = int(time.time())
    entry = {
        "ts": now - 10,
        "cam_id": 1,
        "track_id": 5,
        "label": "vehicle",
        "path": "veh.jpg",
        "plate_path": "plate.jpg",
    }
    redis_client.zadd("vehicle_logs", {json.dumps(entry): entry["ts"]})
    start = datetime.fromtimestamp(now - 60).isoformat()
    end = datetime.fromtimestamp(now).isoformat()
    query = ReportQuery(start=start, end=end, type="vehicle", view="table", rows=10)
    res = asyncio.run(reports._report_data(query))
    assert res["rows"][0]["plate_path"].endswith("plate.jpg")


# Test face report retrieval and export
def test_face_report_table_rows(redis_client, client):
    now = int(time.time() // 60 * 60)
    entry = {
        "ts": now - 30,
        "cam_id": 1,
        "track_id": 7,
        "direction": "in",
        "label": "face123",
        "path": "f.jpg",
    }
    redis_client.zadd("face_logs", {json.dumps(entry): entry["ts"]})
    start = datetime.fromtimestamp(now - 60).strftime("%Y-%m-%d %H:%M")
    end = datetime.fromtimestamp(now).strftime("%Y-%m-%d %H:%M")
    params = {
        "start": start,
        "end": end,
        "type": "face",
        "view": "table",
        "rows": 10,
        "cam_id": "",
        "label": "",
        "cursor": 0,
    }
    res = client.get("/report_data", params=params)
    assert res.status_code == 200
    data = res.json()
    assert len(data["rows"]) == 1
    assert data["rows"][0]["track_id"] == 7


def test_face_report_export(redis_client, client, tmp_path):
    reports.BASE_DIR = tmp_path
    now = int(time.time())
    entry1 = {"ts": now - 120, "in_face": 1, "out_face": 0}
    entry2 = {"ts": now - 60, "in_face": 2, "out_face": 1}
    redis_client.zadd("history", {json.dumps(entry1): entry1["ts"]})
    redis_client.zadd("history", {json.dumps(entry2): entry2["ts"]})
    fentry = {
        "ts": now - 30,
        "cam_id": 1,
        "track_id": 9,
        "direction": "in",
        "label": "face123",
        "path": str(tmp_path / "f.jpg"),
    }
    redis_client.zadd("face_logs", {json.dumps(fentry): fentry["ts"]})
    start = datetime.fromtimestamp(now - 180).strftime("%Y-%m-%d %H:%M")
    end = datetime.fromtimestamp(now).strftime("%Y-%m-%d %H:%M")
    params_graph = {
        "start": start,
        "end": end,
        "type": "face",
        "view": "graph",
        "rows": 50,
        "cam_id": "",
        "label": "",
        "cursor": 0,
    }
    resp_csv = client.get("/report/export", params=params_graph)
    assert resp_csv.status_code == 200
    assert resp_csv.headers["content-type"].startswith("text/csv")
    params_table = {
        "start": start,
        "end": end,
        "type": "face",
        "view": "table",
        "rows": 10,
        "cam_id": "",
        "label": "",
        "cursor": 0,
    }
    resp_xlsx = client.get("/report/export", params=params_table)
    assert resp_xlsx.status_code == 200
    assert resp_xlsx.headers["content-type"].startswith(
        "application/vnd.openxmlformats-officedocument"
    )
