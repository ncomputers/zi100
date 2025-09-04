import json
import queue
import sys
from pathlib import Path

import fakeredis
import numpy as np
from fastapi import FastAPI
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from types import SimpleNamespace

import modules.tracker.manager as manager_mod
from modules.tracker import InferWorker, PersonTracker, PostProcessWorker
from routers import cameras


def test_face_recognition_enables_counting(tmp_path, monkeypatch):
    cfg = {
        "features": {"face_recognition": True},
        "license_info": {"features": {"face_recognition": True}},
        "branding": {},
        "logo_url": "",
        "logo2_url": "",
    }
    cams = [
        {
            "id": 1,
            "name": "C1",
            "url": "u",
            "type": "http",
            "tasks": [],
            "ppe": False,
            "visitor_mgmt": False,
            "face_recognition": False,
            "enable_face_counting": False,
        }
    ]
    r = fakeredis.FakeRedis()
    cameras.init_context(cfg, cams, {}, r, str(tmp_path))
    from config import set_config

    set_config(cfg)
    app = FastAPI()
    app.post("/cameras/{cam_id}/face_recog")(cameras.toggle_face_recog)
    monkeypatch.setattr(cameras, "require_roles", lambda r, roles: True)
    client = TestClient(app)
    resp = client.post("/cameras/1/face_recog")
    assert resp.status_code == 200
    assert cams[0]["face_recognition"] is True
    assert cams[0]["enable_face_counting"] is True


def test_face_crossing_logged(tmp_path, monkeypatch):
    r = fakeredis.FakeRedis()
    tracker = PersonTracker.__new__(PersonTracker)
    tracker.cam_id = 1
    tracker.line_orientation = "vertical"
    tracker.line_ratio = 0.5
    tracker.reverse = False
    tracker.groups = ["person"]
    tracker.in_counts = {}
    tracker.out_counts = {}
    tracker.tracks = {}
    tracker.frame_queue = queue.Queue()
    tracker.det_queue = queue.Queue()
    tracker.out_queue = queue.Queue()
    tracker.running = False
    tracker.viewers = 0
    tracker.snap_dir = Path(tmp_path)
    tracker.redis = r
    tracker.ppe_classes = []
    tracker.cfg = {}
    tracker.debug_stats = {}
    tracker.device = None
    tracker.enable_face_counting = True
    tracker.face_count_conf = 0.5
    tracker.face_count_min_size = 10
    tracker.face_counter = manager_mod.UniqueFaceCounter()
    tracker.batch_size = 1

    import types

    cv2 = types.SimpleNamespace(
        COLOR_BGR2RGB=0,
        cvtColor=lambda img, code: img,
        imwrite=lambda p, img: True,
    )
    monkeypatch.setattr(manager_mod, "cv2", cv2, raising=False)

    frame1 = np.zeros((100, 100, 3), dtype=np.uint8)
    frame2 = np.zeros((100, 100, 3), dtype=np.uint8)
    tracker.frame_queue.put(frame1)
    tracker.frame_queue.put(frame2)

    tracker.model_person = type("M", (), {"names": {0: "person"}})()

    dets = [
        [((10, 10, 20, 20), 0.9, "person")],
        [((70, 10, 20, 20), 0.9, "person")],
    ]

    def fake_detect_batch(frames, groups):
        return [dets.pop(0) for _ in frames]

    tracker.detector = SimpleNamespace(detect_batch=fake_detect_batch)

    class StubTrack:
        def __init__(self, bbox):
            self._bbox = bbox
            self.track_id = 1
            self.det_class = "person"

        def is_confirmed(self):
            return True

        def to_ltrb(self):
            return self._bbox

    bboxes = [(10, 10, 30, 30), (70, 10, 90, 30)]

    class StubDS:
        def __init__(self):
            self.i = 0

        def update_tracks(self, detections, frame=None):
            bbox = bboxes[self.i]
            self.i += 1
            return [StubTrack(bbox)]

    tracker.tracker = StubDS()

    class FakeFace:
        def __init__(self, bbox):
            self.bbox = bbox
            self.det_score = 0.99
            self.embedding = np.ones(512, dtype=np.float32)

    class FakeFD:
        def __init__(self):
            self.i = 0

        def detect(self, img):
            bbox = bboxes[self.i]
            self.i += 1
            return [FakeFace(bbox)]

    monkeypatch.setattr(manager_mod, "FaceDetector", lambda: FakeFD())

    inf = InferWorker(tracker)
    post = PostProcessWorker(tracker)
    inf.run()
    post.run()

    raw = r.zrange("face_logs", 0, -1)
    assert raw
    entry = json.loads(raw[0])
    assert entry["cam_id"] == 1
    assert entry["direction"] == "in"
