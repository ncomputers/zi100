"""Purpose: Test face flow module."""

import asyncio
import base64
import json
import sys
from pathlib import Path

import fakeredis
import numpy as np
from fastapi import FastAPI
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# stub cv2 module
import types


def _imdecode(b, f):
    val = np.frombuffer(b, dtype=np.uint8).sum() % 255
    return np.full((10, 10, 3), val, dtype=np.uint8)


cv2 = types.SimpleNamespace(
    IMREAD_COLOR=1,
    COLOR_BGR2RGB=0,
    COLOR_RGB2BGR=1,
    imdecode=_imdecode,
    cvtColor=lambda a, c: a,
    imwrite=lambda p, img: True,
)
sys.modules["cv2"] = cv2

from modules import face_db

face_db.cv2 = cv2
from routers import api_faces, gatepass


# FakeApp class encapsulates fakeapp behavior
class FakeApp:
    # get routine
    def get(self, img):
        seed = int(img.sum()) % 1000
        rng = np.random.default_rng(seed)
        emb = rng.random(512).astype(np.float32)
        return [type("F", (), {"bbox": [0, 0, 5, 5], "embedding": emb})()]


# setup routine
def setup(tmp_path):
    cfg = {"features": {"visitor_mgmt": True}, "visitor_model": "buffalo_l"}
    r = fakeredis.FakeRedis()
    face_db.FACES_DIR = tmp_path / "public/faces"
    face_db.FAISS_PATH = tmp_path / "public/faiss.index"
    face_db.init(cfg, r)
    face_db.face_app = FakeApp()
    gatepass.init_context(cfg, r, str(tmp_path))
    api_faces.init_context(cfg, r)
    app = FastAPI()
    app.post("/api/faces/add")(api_faces.api_add_face)
    app.post("/api/faces/search")(api_faces.api_search_face)
    client = TestClient(app)
    return cfg, r, client


IDS = [1005, 1009, 1011, 1027, 1024, 1021, 1023, 1050, 1062, 1070]


# fetch_img routine
def fetch_img(i):
    rng = np.random.default_rng(i)
    return rng.integers(0, 256, size=(128, 128, 3), dtype=np.uint8).tobytes()


class DummyRequest:
    base_url = "http://testserver/"


# Test face flow
def test_face_flow(tmp_path):
    cfg, r, client = setup(tmp_path)
    imgs = [fetch_img(i) for i in IDS]
    for idx, img in enumerate(imgs):
        resp = client.post(
            "/api/faces/add",
            data={"visitor_id": f"id{idx}", "threshold": 1.1},
            files={"image": ("a.jpg", img, "image/jpeg")},
        )
        assert resp.status_code == 200
        assert r.hlen("face_db") == idx + 1
        assert face_db.faiss_index.ntotal == idx + 1
        srch = client.post(
            "/api/faces/search", files={"image": ("s.jpg", img, "image/jpeg")}
        ).json()
        assert srch["matches"] and srch["matches"][0]["score"] >= 0.4

    for j in range(5):
        b64 = base64.b64encode(imgs[j]).decode()
        res = asyncio.run(
            gatepass.gatepass_create(
                DummyRequest(),
                name="A",
                phone="1",
                email="",
                host="H",
                purpose="P",
                visitor_type="Official",
                host_department="",
                company_name="C",
                photo=None,
                captured=f"data:image/jpeg;base64,{b64}",
                valid_to="",
                needs_approval="off",
                approver_email="",
            )
        )
        assert res.status_code == 200
    assert face_db.faiss_index.ntotal >= 10
    assert int(r.zcard("vms_logs")) == 5
