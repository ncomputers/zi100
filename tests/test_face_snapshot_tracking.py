"""Ensure best face snapshot is saved and logged."""

import json
import queue
import sys
from pathlib import Path

import fakeredis
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import modules.tracker.manager as manager_mod
from modules.tracker.manager import (
    LightweightFaceTracker,
    PersonTracker,
    PostProcessWorker,
)


class StubFace:
    def __init__(self, bbox, score):
        self.bbox = bbox
        self.det_score = score


class StubDetector:
    def __init__(self, detections):
        self.detections = detections

    def detect(self, rgb):  # pragma: no cover - simple stub
        return self.detections.pop(0)


def test_face_snapshot_tracks_best_frame(monkeypatch, tmp_path):
    r = fakeredis.FakeRedis()
    frame1 = np.full((20, 20, 3), 10, dtype=np.uint8)
    frame2 = np.full((20, 20, 3), 20, dtype=np.uint8)
    dets = [
        [StubFace([0, 0, 10, 10], 0.5)],
        [StubFace([0, 0, 10, 10], 0.9)],
    ]
    tracker = PersonTracker.__new__(PersonTracker)
    tracker.cam_id = 1
    tracker.frame_queue = queue.Queue()
    tracker.det_queue = queue.Queue()
    tracker.out_queue = queue.Queue()
    tracker.det_queue.put((frame1, []))
    tracker.det_queue.put((frame2, []))
    tracker.running = False
    tracker.viewers = 0
    tracker.snap_dir = Path(tmp_path)
    tracker.redis = r
    tracker.face_detector = StubDetector(dets)
    tracker.face_tracker = LightweightFaceTracker()
    tracker.face_best = {}
    tracker.face_active_ids = set()
    tracker.face_tracking_enabled = True
    tracker.face_db_enabled = True
    tracker.device = None
    tracker.tracks = {}
    tracker.groups = ["person"]
    tracker.line_orientation = "vertical"
    tracker.line_ratio = 0.5
    tracker.tracker = None
    tracker.cfg = {"features": {"face_recognition": True, "in_out_counting": True}}
    tracker.debug_stats = {}

    # stub imwrite to save raw bytes
    monkeypatch.setattr(
        manager_mod.cv2,
        "imwrite",
        lambda p, img: Path(p).write_bytes(img.tobytes()) or True,
        raising=False,
    )

    inserted = []
    import modules.face_db as face_db_mod

    monkeypatch.setattr(
        face_db_mod,
        "insert",
        lambda data, pid, **kw: inserted.append(data) or (True, []),
    )

    worker = PostProcessWorker(tracker)
    worker.run()

    raw = r.zrange("face_logs", 0, -1)[0]
    log = json.loads(raw)
    path = log["path"]
    assert log["track_id"] == 0
    data = Path(path).read_bytes()
    assert data == frame2[0:10, 0:10].tobytes()
    assert inserted and inserted[0] == data


def test_process_faces_handles_none_conf(monkeypatch, tmp_path):
    class StubTrack:
        def __init__(self):
            self.track_id = 1
            self.det_conf = None

        def is_confirmed(self):
            return True

        def to_ltrb(self):  # noqa: D401 - simple stub
            return [0, 0, 10, 10]

    class StubFaceTracker:
        def update_tracks(self, ds_dets, frame=None):  # pragma: no cover - stub
            return [StubTrack()]

    frame = np.zeros((20, 20, 3), dtype=np.uint8)
    tracker = PersonTracker.__new__(PersonTracker)
    tracker.cam_id = 1
    tracker.snap_dir = Path(tmp_path)
    tracker.face_detector = StubDetector([[StubFace([0, 0, 10, 10], 0.9)]])
    tracker.face_tracker = StubFaceTracker()
    tracker.face_best = {}
    tracker.face_active_ids = set()
    tracker.redis = fakeredis.FakeRedis()

    monkeypatch.setattr(manager_mod.cv2, "imwrite", lambda *a, **kw: True)

    tracker._process_faces(frame)

    assert tracker.face_best[1][0] == 0.0
