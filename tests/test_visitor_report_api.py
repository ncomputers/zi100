"""Test visitor report API includes gate pass entries."""

import json
import sys
import time
from pathlib import Path

import fakeredis
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
google_sa = types.SimpleNamespace(Credentials=object)
google_creds = types.SimpleNamespace(Credentials=object)
sys.modules.setdefault("google.oauth2.service_account", google_sa)
sys.modules.setdefault("google.oauth2.credentials", google_creds)
sys.modules.setdefault(
    "google.oauth2",
    types.SimpleNamespace(service_account=google_sa, credentials=google_creds),
)
sys.modules.setdefault(
    "google_auth_oauthlib",
    types.SimpleNamespace(flow=types.SimpleNamespace(InstalledAppFlow=object)),
)
sys.modules.setdefault(
    "google_auth_oauthlib.flow", types.SimpleNamespace(InstalledAppFlow=object)
)

from routers import visitor
from routers.visitor import registration


def test_api_visitor_report_returns_gatepass(tmp_path):
    cfg = {"features": {"visitor_mgmt": True}, "visitor_model": "buffalo_l"}
    r = fakeredis.FakeRedis()
    visitor.init_context(cfg, r, str(tmp_path), [])
    registration.redis = visitor.get_context().redis
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
    res = client.get("/api/visitor-report")
    assert res.status_code == 200
    data = res.json()
    gids = {v["gate_id"] for v in data["items"]}
    assert entry["gate_id"] in gids


def test_api_visitor_report_redis_unavailable(tmp_path):
    cfg = {"features": {"visitor_mgmt": True}, "visitor_model": "buffalo_l"}
    visitor.init_context(cfg, None, str(tmp_path), [])
    registration.redis = visitor.get_context().redis
    app = FastAPI()
    app.include_router(registration.router)
    client = TestClient(app)
    res = client.get("/api/visitor-report")
    assert res.status_code == 503
    assert res.json()["detail"] == "redis_unavailable"
