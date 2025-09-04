import sys
from pathlib import Path

import fakeredis
from fastapi import FastAPI
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from modules import face_db  # noqa: E402
from routers.visitor import faces as faces_router  # noqa: E402


def setup_app(tmp_path):
    cfg = {"features": {"visitor_mgmt": True}, "visitor_model": "buffalo_l"}
    r = fakeredis.FakeRedis()
    face_db.FACES_DIR = tmp_path / "public/faces"
    face_db.FACES_DIR.mkdir(parents=True)
    face_db.init(cfg, r)
    faces_router.config_obj = cfg
    faces_router.redis = r
    app = FastAPI()
    app.post("/reembed_face")(faces_router.reembed_face)
    client = TestClient(app)
    return client, r


def test_reembed_queues_id(tmp_path):
    client, r = setup_app(tmp_path)
    fid = "1" * 32
    resp = client.post("/reembed_face", data={"face_id": fid})
    assert resp.status_code == 200
    assert r.lpop(face_db.REEMBED_QUEUE) == fid.encode()


def test_reembed_rejects_invalid_id(tmp_path):
    client, _ = setup_app(tmp_path)
    resp = client.post("/reembed_face", data={"face_id": "bad$id"})
    assert resp.status_code == 400
