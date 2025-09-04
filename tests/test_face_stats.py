"""Tests for /api/faces/stats endpoint."""

import fakeredis
from fastapi import FastAPI
from fastapi.testclient import TestClient

from routers import api_faces


def test_face_stats_returns_counts():
    cfg = {"enable_face_recognition": False}
    r = fakeredis.FakeRedis()
    api_faces.init_context(cfg, r)
    r.sadd("face:known_ids", "k1", "k2")
    r.sadd("face:unregistered_ids", "u1")
    r.sadd("face:pending_ids", "p1", "p2", "p3")
    r.sadd("face:deleted_ids", "d1")
    app = FastAPI()
    app.include_router(api_faces.router)
    client = TestClient(app)
    resp = client.get("/api/faces/stats")
    assert resp.status_code == 200
    assert resp.json() == {
        "known_count": 2,
        "unregistered_count": 1,
        "pending_count": 3,
        "deleted_count": 1,
    }
