import fakeredis
from fastapi import FastAPI
from fastapi.testclient import TestClient

from routers import api_faces
from utils.deps import get_cameras


def _make_client() -> TestClient:
    cfg = {"enable_face_recognition": False}
    r = fakeredis.FakeRedis()
    api_faces.init_context(cfg, r)
    app = FastAPI()
    app.dependency_overrides[get_cameras] = lambda: []
    app.include_router(api_faces.router)
    api_faces.require_roles = lambda request, roles: {"role": "admin"}
    return TestClient(app)


def test_limit_out_of_range_returns_422():
    client = _make_client()
    assert client.get("/api/faces", params={"limit": 0}).status_code == 422
    assert client.get("/api/faces", params={"limit": 101}).status_code == 422


def test_invalid_dates_return_422():
    client = _make_client()
    assert client.get("/api/faces", params={"from": "bad"}).status_code == 422
    assert client.get("/api/faces", params={"to": "also-bad"}).status_code == 422


def test_malformed_cursor_returns_400():
    client = _make_client()
    resp = client.get("/api/faces", params={"cursor": "bad"})
    assert resp.status_code == 400
    assert resp.json() == {"error": "invalid_cursor"}


def test_faces_include_new_fields():
    client = _make_client()
    r = api_faces.face_db.redis_client
    r.sadd("face:known_ids", "1")
    r.hset(
        "face:known:1",
        mapping={"name": "A", "captured_at": 1, "embedding": "[]"},
    )
    resp = client.get("/api/faces")
    assert resp.status_code == 200
    data = resp.json()["faces"][0]
    assert "captured_at" in data
    assert "similarity_candidates" in data
