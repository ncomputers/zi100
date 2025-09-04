import pytest
import fakeredis
from fastapi import FastAPI
from fastapi.testclient import TestClient

from modules import face_db
from routers import api_faces, visitor
from routers.visitor import faces as visitor_faces
from utils.deps import get_cameras


class DummyIdx:
    def __init__(self):
        self.ntotal = 0

    def add(self, vecs):
        self.ntotal += len(vecs)

    def search(self, vecs, k):
        return [[0.0] * k], [[-1] * k]


@pytest.fixture
def api_client(tmp_path, monkeypatch):
    cfg = {"features": {"visitor_mgmt": True}}
    r = fakeredis.FakeRedis(decode_responses=True)
    face_db.FACES_DIR = tmp_path / "faces"
    face_db.FAISS_PATH = tmp_path / "faiss.index"
    face_db.init(cfg, r)
    monkeypatch.setattr(face_db, "faiss_index", DummyIdx())
    monkeypatch.setattr(face_db, "remove_from_index", lambda fid: None)
    visitor.init_context(cfg, r, str(tmp_path))
    api_faces.init_context(cfg, r)
    app = FastAPI()
    app.include_router(api_faces.router)
    app.include_router(visitor_faces.router)
    app.dependency_overrides[visitor_faces.require_admin] = lambda: {"name": "admin"}
    app.dependency_overrides[get_cameras] = lambda: []
    monkeypatch.setattr(visitor_faces, "_log_face_action", lambda *a, **k: None)
    return r, TestClient(app)


def _seed_faces(r):
    faces = {
        "1": {"name": "alice", "last_seen_at": "100", "first_seen_at": "90"},
        "2": {"name": "bob", "last_seen_at": "90", "first_seen_at": "80"},
        "3": {"name": "carol", "last_seen_at": "90", "first_seen_at": "70"},
    }
    for fid, mapping in faces.items():
        r.sadd("face:known_ids", fid)
        r.hset(f"face:known:{fid}", mapping=mapping)


def test_filter_sort_cursor(api_client):
    r, client = api_client
    _seed_faces(r)
    resp = client.get("/api/faces?limit=2&sort=last_seen_desc")
    data = resp.json()
    assert [f["id"] for f in data["faces"]] == ["1", "3"]
    next_cursor = data["next_cursor"]
    resp2 = client.get(f"/api/faces?limit=2&cursor={next_cursor}")
    assert [f["id"] for f in resp2.json()["faces"]] == ["2"]
    resp3 = client.get("/api/faces?q=bob")
    assert [f["id"] for f in resp3.json()["faces"]] == ["2"]


def test_attach_and_merge(api_client, monkeypatch):
    r, client = api_client
    calls = []

    def fake_add(data, visitor_id, merge_on_match=True, threshold=0.95):
        calls.append((visitor_id, merge_on_match))
        return True

    monkeypatch.setattr(face_db, "add_face_if_single_detected", fake_add)
    resp = client.post(
        "/api/faces/add",
        data={"visitor_id": "abc"},
        files={"image": ("a.jpg", b"x", "image/jpeg")},
    )
    assert resp.json() == {"added": True}
    resp = client.post(
        "/api/faces/add",
        data={"visitor_id": "abc", "merge_on_match": "false"},
        files={"image": ("a.jpg", b"x", "image/jpeg")},
    )
    assert resp.json() == {"added": True}
    assert calls == [("abc", True), ("abc", False)]


def test_delete_flow(api_client):
    r, client = api_client
    fid = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
    r.sadd("face:known_ids", fid)
    r.hset(f"face:known:{fid}", mapping={"name": "alice"})
    resp = client.post("/delete_faces", data={"face_ids": fid, "reason": "dup"})
    assert resp.json()["deleted"]
    assert not r.sismember("face:known_ids", fid)
    assert r.sismember("face:deleted_ids", fid)


def test_update_status(api_client):
    r, client = api_client
    fid = "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
    r.sadd("face:pending_ids", fid)
    r.hset(f"face:pending:{fid}", mapping={"name": ""})
    resp = client.post(f"/api/faces/{fid}/status", json={"status": "unregistered"})
    assert resp.json() == {"status": "unregistered"}
    assert r.sismember("face:unregistered_ids", fid)
    assert not r.sismember("face:pending_ids", fid)


@pytest.mark.xfail(reason="ban flow not implemented")
def test_ban_flow():
    pass


@pytest.mark.xfail(reason="training job flow not implemented")
def test_training_job_flow():
    pass
