import base64
import io
import sys
from pathlib import Path

import fakeredis
import numpy as np
from fastapi import FastAPI
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from config import set_config, config as global_config
from core.config import CONFIG_DEFAULTS
from modules import face_db
from routers import face_db as face_router


class CV2Stub:
    IMREAD_COLOR = 1
    COLOR_BGR2RGB = 0

    @staticmethod
    def imdecode(b, flag):
        return np.zeros((10, 10, 3), dtype=np.uint8)

    @staticmethod
    def cvtColor(a, code):
        return a


def make_image_b64() -> str:
    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (10, 10), "red").save(buf, format="JPEG")
    return base64.b64encode(buf.getvalue()).decode()


def setup_app(monkeypatch, enabled: bool = True):
    cfg = {**CONFIG_DEFAULTS}
    cfg["features"] = {**CONFIG_DEFAULTS.get("features", {}), "visitor_mgmt": True}
    cfg["enable_face_recognition"] = enabled
    set_config(cfg)
    assert 0.0 <= global_config["face_match_thresh"] <= 1.0
    r = fakeredis.FakeRedis()
    face_db.cv2 = CV2Stub
    face_router.cv2 = CV2Stub
    face_db.init(cfg, r)
    face_router.init_context(cfg, r)
    if enabled:
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

        class Idx:
            ntotal = 1

            def search(self, arr, k):
                return np.array([[0.9]], dtype=np.float32), np.array([[0]])

        face_db.faiss_index = Idx()
        face_db.id_map = ["p1"]
        r.hset("face:known:p1", mapping={"name": "Alice"})
    app = FastAPI()
    app.include_router(face_router.router)
    return TestClient(app)


def test_process_frame_valid(monkeypatch):
    client = setup_app(monkeypatch)
    payload = {
        "image": make_image_b64(),
        "scaleFactor": 1.1,
        "minNeighbors": 5,
        "minFaceSize": 60,
    }
    resp = client.post("/process_frame", json=payload)
    assert resp.status_code == 200
    faces = resp.json()["faces"]
    assert faces and faces[0]["name"] == "Alice"
    assert faces[0]["id"] == "p1"


def test_process_frame_invalid(monkeypatch):
    client = setup_app(monkeypatch)
    resp = client.post("/process_frame", json={"scaleFactor": 1.1})
    assert resp.status_code == 400


def test_process_frame_disabled(monkeypatch):
    client = setup_app(monkeypatch, enabled=False)
    payload = {
        "image": make_image_b64(),
        "scaleFactor": 1.1,
        "minNeighbors": 5,
        "minFaceSize": 60,
    }
    resp = client.post("/process_frame", json=payload)
    assert resp.status_code == 403


def test_process_frame_bounds(monkeypatch):
    client = setup_app(monkeypatch)
    img = make_image_b64()
    # scale factor too low
    resp = client.post(
        "/process_frame",
        json={"image": img, "scaleFactor": 0.4, "minNeighbors": 5, "minFaceSize": 60},
    )
    assert resp.status_code == 400
    # scale factor too high
    resp = client.post(
        "/process_frame",
        json={"image": img, "scaleFactor": 1.6, "minNeighbors": 5, "minFaceSize": 60},
    )
    assert resp.status_code == 400
    # neighbors out of range
    resp = client.post(
        "/process_frame",
        json={"image": img, "scaleFactor": 1.1, "minNeighbors": 0, "minFaceSize": 60},
    )
    assert resp.status_code == 400
    # min face size out of range
    resp = client.post(
        "/process_frame",
        json={"image": img, "scaleFactor": 1.1, "minNeighbors": 5, "minFaceSize": 10},
    )
    assert resp.status_code == 400
