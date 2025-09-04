"""Test report router."""

import json
import time
from datetime import datetime

import fakeredis
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from routers import reports
from utils.time import format_ts


@pytest.fixture
def redis_client():
    return fakeredis.FakeRedis()


@pytest.fixture(autouse=True)
def setup_context(redis_client, tmp_path):
    reports.init_context({}, {}, redis_client, str(tmp_path), [])


@pytest.fixture
def client(monkeypatch):
    app = FastAPI()
    app.include_router(reports.router)
    monkeypatch.setattr(reports, "require_roles", lambda request, roles: True)
    return TestClient(app)


def test_report_data_time_field_format(redis_client, client):
    now = int(time.time())
    entry = {
        "ts": now,
        "cam_id": 1,
        "track_id": 1,
        "direction": "in",
        "label": "person",
    }
    redis_client.zadd("person_logs", {json.dumps(entry): entry["ts"]})
    start = datetime.fromtimestamp(now - 60).strftime("%Y-%m-%d %H:%M")
    end = datetime.fromtimestamp(now + 60).strftime("%Y-%m-%d %H:%M")
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
    assert data["rows"][0]["time"] == format_ts(entry["ts"], "%Y-%m-%d %H:%M")
