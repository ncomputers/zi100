import fakeredis
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from routers import visitor


def test_delete_faces_reason_field(monkeypatch, tmp_path):
    cfg = {"features": {"visitor_mgmt": True}, "visitor_model": "buffalo_l"}
    r = fakeredis.FakeRedis()
    visitor.init_context(cfg, r, str(tmp_path), [])
    monkeypatch.setattr(
        visitor.faces,
        "_log_face_action",
        lambda *args, **kwargs: None,
        raising=False,
    )

    fid = "1" * 32
    r.hset(f"face:known:{fid}", mapping={"image_path": "/tmp/a.jpg"})
    r.sadd("face:known_ids", fid)

    app = FastAPI()
    app.include_router(visitor.router)

    def _admin(request: Request):
        return {"role": "admin", "name": "Tester"}

    app.dependency_overrides[visitor.faces.require_admin] = _admin
    client = TestClient(app)

    resp = client.post("/delete_faces", data={"face_ids": fid, "reason": "duplicate"})
    assert resp.status_code == 200
    data = {k.decode(): v.decode() for k, v in r.hgetall(f"face:deleted:{fid}").items()}
    assert data["reason"] == "duplicate"

    fid2 = "2" * 32
    r.hset(f"face:known:{fid2}", mapping={"image_path": "/tmp/b.jpg"})
    r.sadd("face:known_ids", fid2)

    resp2 = client.post("/delete_faces", data={"face_ids": fid2, "reason": ""})
    assert resp2.status_code == 200
    data2 = {
        k.decode(): v.decode() for k, v in r.hgetall(f"face:deleted:{fid2}").items()
    }
    assert "reason" not in data2


def test_delete_faces_rejects_invalid_id(monkeypatch, tmp_path):
    cfg = {"features": {"visitor_mgmt": True}, "visitor_model": "buffalo_l"}
    r = fakeredis.FakeRedis()
    visitor.init_context(cfg, r, str(tmp_path), [])
    app = FastAPI()
    app.include_router(visitor.router)

    def _admin(request: Request):
        return {"role": "admin", "name": "Tester"}

    app.dependency_overrides[visitor.faces.require_admin] = _admin
    client = TestClient(app)
    resp = client.post("/delete_faces", data={"face_ids": "bad$id", "reason": ""})
    assert resp.status_code == 400
