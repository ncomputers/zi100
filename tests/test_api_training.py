import fakeredis
from fastapi import FastAPI
from fastapi.testclient import TestClient

from routers import api_training


def _client():
    r = fakeredis.FakeRedis()
    api_training.init_context({}, r)
    app = FastAPI()
    app.include_router(api_training.router)
    api_training.require_roles = lambda request, roles: {"role": "admin"}
    return TestClient(app), r


def test_start_and_status():
    client, r = _client()
    assert client.get("/api/training/status").json()["status"] == "idle"
    client.post("/api/training/start")
    assert client.get("/api/training/status").json()["status"] == "running"
