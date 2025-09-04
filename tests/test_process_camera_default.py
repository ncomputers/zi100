import sys
from pathlib import Path

import fakeredis
import numpy as np
from fastapi import FastAPI
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from config import config, set_config
from modules import face_db
from routers import face_db as face_router


class CV2Stub:
    COLOR_BGR2RGB = 0

    def cvtColor(self, a, b):
        return a

    def imencode(self, ext, img):
        return True, np.zeros(1, dtype=np.uint8)


cv2_stub = CV2Stub()
face_db.cv2 = cv2_stub
face_router.cv2 = cv2_stub


def setup_app(monkeypatch):
    cfg = {"features": {"visitor_mgmt": True}}
    set_config(cfg)
    assert config.get("face_match_thresh") == 0.5
    r = fakeredis.FakeRedis()
    face_db.init(cfg, r)
    face_router.init_context(cfg, r)
    face_db.cv2 = cv2_stub
    face_router.cv2 = cv2_stub
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

    class Cap:
        def read(self):
            return True, np.zeros((10, 10, 3), dtype=np.uint8)

        def release(self):
            pass

    def open_capture_stub(*args, **kwargs):
        return Cap(), "tcp"

    face_router.open_capture = open_capture_stub

    app = FastAPI()
    app.include_router(face_router.router)
    app.state.cameras = [
        {
            "id": 1,
            "url": "",
            "type": "http",
            "resolution": "640x480",
            "rtsp_transport": "tcp",
            "stream_mode": "gstreamer",
            "use_gpu": False,
            "capture_buffer": 1,
        }
    ]
    return TestClient(app)


def test_process_camera_default_threshold(monkeypatch):
    client = setup_app(monkeypatch)
    resp = client.get("/process_camera/1")
    assert resp.status_code == 200
    data = resp.json()
    assert data["faces"] and data["faces"][0]["id"] == "p1"
