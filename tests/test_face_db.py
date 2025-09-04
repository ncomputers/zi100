"""Purpose: Test face db module."""

import io
import json
import sys
from pathlib import Path

import fakeredis
import numpy as np
from fastapi import FastAPI
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


class CV2Stub:
    IMREAD_COLOR = 1
    COLOR_BGR2RGB = 0
    COLOR_RGB2BGR = 1
    last_saved = None

    @staticmethod
    def imdecode(b, f):
        return np.zeros((10, 10, 3), dtype=np.uint8)

    @staticmethod
    def cvtColor(a, c):
        return a

    @staticmethod
    def imwrite(p, img):
        CV2Stub.last_saved = img
        return True


sys.modules["cv2"] = CV2Stub

from modules import face_db
from routers import api_faces


# make_image routine
def make_image() -> bytes:
    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (10, 10), "red").save(buf, format="JPEG")
    return buf.getvalue()


# setup routine
class IndexStub:
    def __init__(self):
        self.vecs = []

    def add(self, arr):
        self.vecs.extend(arr)

    @property
    def ntotal(self):
        return len(self.vecs)

    def search(self, arr, k):
        if not self.vecs:
            return np.zeros((1, k), dtype="float32"), np.full((1, k), -1)
        mat = np.stack(self.vecs)
        sims = mat @ arr.T
        idx = np.argsort(-sims, axis=0)[:k].T
        D = np.take_along_axis(sims.T, idx, axis=1)
        return D.astype("float32"), idx


def setup(tmp_path):
    cfg = {"features": {"visitor_mgmt": True}, "visitor_model": "buffalo_l"}
    r = fakeredis.FakeRedis()
    sys.modules["cv2"] = CV2Stub
    face_db.cv2 = CV2Stub
    face_db.FACES_DIR = tmp_path / "public/faces"
    face_db.FACES_DIR.mkdir(parents=True)
    face_db.init(cfg, r)
    api_faces.init_context(cfg, r)
    index = IndexStub()
    return cfg, r, index


# Test add face updates db
def test_add_face_updates_db(tmp_path, monkeypatch):
    _cfg, r, index = setup(tmp_path)
    app = FastAPI()
    app.post("/api/faces/add")(api_faces.api_add_face)
    client = TestClient(app)

    monkeypatch.setattr(
        face_db,
        "face_app",
        type(
            "A",
            (),
            {
                "get": lambda self, img: [
                    type(
                        "F",
                        (),
                        {
                            "bbox": [0, 0, 5, 5],
                            "embedding": np.ones(512, dtype=np.float32),
                        },
                    )()
                ]
            },
        )(),
    )

    img = make_image()
    resp = client.post(
        "/api/faces/add",
        data={"visitor_id": "v1"},
        files={"image": ("a.jpg", img, "image/jpeg")},
    )
    assert resp.status_code == 200
    data = json.loads(r.hget("face_db", "v1"))
    assert len(data["embedding"]) == 512
    fields = {
        k.decode(): v.decode() if isinstance(v, bytes) else v
        for k, v in r.hgetall("face:known:v1").items()
    }
    assert fields.get("model_version") == "buffalo_l"

    index.add(np.zeros((1, 512), dtype=np.float32))
    prev = int(index.ntotal)
    face_db.redis_client = r
    face_db.add_face("v2", img, threshold=1.1)
    assert int(index.ntotal) == prev  # worker not auto in this test
    assert r.hexists("face_db", "v2")


def test_add_face_multiple_faces_error(tmp_path, monkeypatch):
    _cfg, _r, _index = setup(tmp_path)
    app = FastAPI()
    app.post("/api/faces/add")(api_faces.api_add_face)
    client = TestClient(app)

    # Simulate detection of multiple faces
    monkeypatch.setattr(
        face_db,
        "add_face_if_single_detected",
        lambda *args, **kwargs: False,
    )

    img = make_image()
    resp = client.post(
        "/api/faces/add",
        data={"visitor_id": "v1"},
        files={"image": ("a.jpg", img, "image/jpeg")},
    )
    assert resp.status_code == 400
    assert resp.json() == {
        "ok": False,
        "code": "multiple_faces_detected",
        "message": "Multiple faces detected",
    }


def test_insert_manual_saves_cropped_face(tmp_path, monkeypatch):
    cfg, r, _ = setup(tmp_path)
    monkeypatch.setattr(
        face_db,
        "face_app",
        type(
            "A",
            (),
            {
                "get": lambda self, img: [
                    type(
                        "F",
                        (),
                        {
                            "bbox": [0, 0, 5, 5],
                            "embedding": np.ones(512, dtype=np.float32),
                        },
                    )()
                ]
            },
        )(),
    )
    img = make_image()
    cv2 = sys.modules["cv2"]
    cv2.last_saved = None
    ok, _ = face_db.insert(img, "p1", source="manual")
    assert ok
    assert cv2.last_saved.shape == (5, 5, 3)


def test_insert_non_manual_saves_cropped_face(tmp_path, monkeypatch):
    cfg, r, _ = setup(tmp_path)
    monkeypatch.setattr(
        face_db,
        "face_app",
        type(
            "A",
            (),
            {
                "get": lambda self, img: [
                    type(
                        "F",
                        (),
                        {
                            "bbox": [0, 0, 5, 5],
                            "embedding": np.ones(512, dtype=np.float32),
                        },
                    )()
                ]
            },
        )(),
    )
    img = make_image()
    cv2 = sys.modules["cv2"]
    cv2.last_saved = None
    ok, _ = face_db.insert(img, "p2")
    assert ok
    assert cv2.last_saved.shape == (5, 5, 3)


# Test manual insert populates known ids and search
def test_manual_insert_search(tmp_path, monkeypatch):
    cfg = {
        "features": {"visitor_mgmt": True, "face_recognition": True},
        "visitor_model": "buffalo_l",
    }
    r = fakeredis.FakeRedis()
    face_db.FACES_DIR = tmp_path / "public/faces"
    face_db.FAISS_PATH = tmp_path / "public/faiss.index"
    face_db.FACES_DIR.mkdir(parents=True)
    from config import set_config

    set_config(cfg)
    face_db.init(cfg, r)

    # consistent embedding for insert/search
    monkeypatch.setattr(
        face_db,
        "face_app",
        type(
            "A",
            (),
            {
                "get": lambda self, img: [
                    type(
                        "F",
                        (),
                        {
                            "bbox": [0, 0, 5, 5],
                            "embedding": np.ones(512, dtype=np.float32),
                        },
                    )()
                ]
            },
        )(),
    )

    from modules.face_engine.router import router as face_router

    app = FastAPI()
    app.include_router(face_router)
    client = TestClient(app)

    img = make_image()
    resp = client.post(
        "/face/insert",
        data={"person_id": "p1", "source": "manual"},
        files={"image": ("a.jpg", img, "image/jpeg")},
    )
    assert resp.status_code == 200 and resp.json()["inserted"]
    assert r.hexists("face:known:p1", "embedding")
    assert r.sismember("face:known_ids", "p1")

    resp = client.post("/face/search", files={"image": ("b.jpg", img, "image/jpeg")})
    matches = resp.json()["matches"]
    assert matches and matches[0]["id"] == "manual:p1"


def test_insert_preserves_existing_name(tmp_path, monkeypatch):
    cfg, r, _ = setup(tmp_path)
    r.hset("face:known:p1", mapping={"name": "Alice"})
    monkeypatch.setattr(
        face_db,
        "face_app",
        type(
            "A",
            (),
            {
                "get": lambda self, img: [
                    type(
                        "F",
                        (),
                        {
                            "bbox": [0, 0, 5, 5],
                            "embedding": np.ones(512, dtype=np.float32),
                        },
                    )()
                ]
            },
        )(),
    )
    img = make_image()
    face_db.insert(img, "p1")
    assert r.hget("face:known:p1", "name").decode() == "Alice"


def test_unregistered_candidate_cache(tmp_path, monkeypatch):
    cfg, r, _ = setup(tmp_path)
    face_db.redis_client = r
    index = IndexStub()
    emb_known = np.ones(512, dtype=np.float32)
    emb_known /= np.linalg.norm(emb_known)
    index.add(emb_known.reshape(1, -1))
    face_db.faiss_index = index
    face_db.id_map = ["manual:k1"]
    r.hset("face:known:k1", mapping={"embedding": json.dumps(emb_known.tolist())})
    emb_unreg = emb_known.copy()
    r.hset("face:known:u1", mapping={"embedding": json.dumps(emb_unreg.tolist())})
    face_db.cache_unregistered_candidates("u1", emb_unreg)
    matches = face_db.get_top_matches("u1", 0.5)
    assert matches and matches[0]["id"] == "manual:k1"
    assert face_db.get_top_matches("u1", 1.1) == []
