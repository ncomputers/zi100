from pathlib import Path
import sys

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
    COLOR_BGR2RGB = 0

    @staticmethod
    def cvtColor(a, b):
        return a

    @staticmethod
    def imencode(ext, img):
        # return success flag and fake buffer
        return True, np.zeros(1, dtype=np.uint8)


def setup_app(monkeypatch):
    cfg = {**CONFIG_DEFAULTS}
    cfg["features"] = {**CONFIG_DEFAULTS.get("features", {}), "visitor_mgmt": True}
    set_config(cfg)
    assert 0.0 <= global_config["face_match_thresh"] <= 1.0
    r = fakeredis.FakeRedis()
    face_db.cv2 = CV2Stub
    face_router.cv2 = CV2Stub
    face_db.init(cfg, r)
    face_router.init_context(cfg, r)
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
            "url": "",  # not used
            "type": "http",
            "resolution": "640x480",
            "rtsp_transport": "tcp",
            "stream_mode": "gstreamer",
            "use_gpu": False,
            "capture_buffer": 1,
        }
    ]
    return TestClient(app)


def test_process_camera(monkeypatch):
    client = setup_app(monkeypatch)
    resp = client.get("/process_camera/1")
    assert resp.status_code == 200
    data = resp.json()
    assert "image" in data
    assert data["faces"] and data["faces"][0]["name"] == "Alice"
