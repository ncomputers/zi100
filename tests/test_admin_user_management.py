import asyncio
import json

import fakeredis
import pytest
from fastapi import FastAPI
from fastapi.templating import Jinja2Templates
from fastapi.testclient import TestClient

from modules import gatepass_service
from modules import utils as module_utils
from modules import visitor_db
from routers import gatepass
from routers import visitor as visitor_router
from routers.admin import users as admin_users


@pytest.fixture
def admin_client(monkeypatch, tmp_path):
    config = {"users": []}
    app = FastAPI()
    app.include_router(admin_users.router)
    app.state.config = config
    app.state.redis_client = None
    app.state.templates = Jinja2Templates(directory=str(tmp_path))
    app.state.config_path = str(tmp_path / "cfg.json")
    app.dependency_overrides[module_utils.require_admin] = lambda: {"name": "tester"}
    monkeypatch.setattr(admin_users, "save_config", lambda *_: None)
    return TestClient(app)


def test_create_user_without_password(admin_client):
    r = admin_client.post(
        "/admin/users", json={"username": "alice", "role": "admin", "modules": []}
    )
    assert r.status_code == 422


def test_mfa_toggle(admin_client):
    r = admin_client.post(
        "/admin/users",
        json={
            "username": "bob",
            "password": "pw",
            "role": "admin",
            "modules": [],
        },
    )
    assert r.status_code == 200
    assert admin_client.app.state.config["users"][0]["mfa_enabled"] is False
    r = admin_client.put("/admin/users/bob", json={"mfa_enabled": True})
    assert r.status_code == 200
    assert admin_client.app.state.config["users"][0]["mfa_enabled"] is True


def test_cannot_delete_last_admin(admin_client):
    admin_client.post(
        "/admin/users",
        json={"username": "a", "password": "x", "role": "admin", "modules": []},
    )
    admin_client.post(
        "/admin/users",
        json={"username": "b", "password": "x", "role": "admin", "modules": []},
    )
    assert admin_client.delete("/admin/users/b").status_code == 200
    resp = admin_client.delete("/admin/users/a")
    assert resp.status_code == 400
    assert resp.json()["detail"] == "cannot_delete_last_admin"


@pytest.fixture
def redis_client():
    r = fakeredis.FakeRedis(decode_responses=True)
    visitor_db.init_db(r)
    gatepass_service.init(r)
    gatepass.redis = r
    visitor_router.redis = r
    visitor_router.config_obj = {
        "features": {"visitor_mgmt": True},
        "base_url": "http://test",
    }
    gatepass.config_obj = {"features": {"visitor_mgmt": True}}
    return r


@pytest.fixture
def invite_client(redis_client):
    app = FastAPI()
    app.include_router(visitor_router.router)
    return TestClient(app)


def test_invite_status_transitions(invite_client, redis_client):
    resp = invite_client.post(
        "/invite/create",
        data={
            "name": "Jane",
            "phone": "555",
            "email": "",
            "visitor_type": "guest",
            "company": "Corp",
            "host": "Host",
            "visit_time": "2024-01-01T00:00",
            "expiry": "",
            "purpose": "Meet",
            "photo": "",
            "send_mail": "off",
            "no_photo": "on",
        },
    )
    iid = resp.json()["id"]
    invite_client.put(f"/invite/hold/{iid}")
    invite_client.put(f"/invite/approve/{iid}")
    invite_client.put(f"/invite/reject/{iid}")
    entries = [json.loads(e) for e in redis_client.zrevrange("invite_records", 0, -1)]
    statuses = {e["status"] for e in entries if e["id"] == iid}
    assert statuses.issuperset({"hold", "approved", "rejected"})
