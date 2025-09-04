"""Tests for dashboard stats API."""

import fakeredis
import pytest
from fakeredis.aioredis import FakeRedis as AsyncFakeRedis
from fastapi.testclient import TestClient

import app
from config import config as cfg
from utils import preflight
from utils import redis as redis_utils


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(
        app,
        "get_sync_client",
        lambda url=None: fakeredis.FakeRedis(decode_responses=True),
    )
    monkeypatch.setattr(
        redis_utils,
        "get_sync_client",
        lambda url=None: fakeredis.FakeRedis(decode_responses=True),
    )

    async def _fake_get_client(url: str | None = None):
        return AsyncFakeRedis(decode_responses=True)

    monkeypatch.setattr(redis_utils, "get_client", _fake_get_client)
    preflight.check_dependencies = lambda *a, **k: None
    app.init_app()
    app.app.state.config.setdefault("features", {})["visitor_mgmt"] = True
    cfg.setdefault("features", {})["visitor_mgmt"] = True
    with TestClient(app.app) as c:
        c.post("/login", data={"username": "admin", "password": "rapidadmin"})
        yield c


def test_dashboard_stats_default_entry_exit(client):
    resp = client.get("/api/dashboard/stats")
    assert resp.status_code == 200
