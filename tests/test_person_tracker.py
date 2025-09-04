import queue
import sys
from pathlib import Path
from types import SimpleNamespace

import fakeredis
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import modules.tracker.detector as det  # noqa: E402
from modules.tracker import (  # noqa: E402
    InferWorker,
    PersonTracker,
    PostProcessWorker,
    ProcessingWorker,
)


def test_zone_change_cooldown(monkeypatch, tmp_path):
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
    tracker.count_cooldown = 2
    tracker._counted = {}
    tracker.detector_fps = 0

    frame = np.zeros((100, 100, 3), dtype=np.uint8)
    for _ in range(3):
        tracker.frame_queue.put(frame)

    tracker.model_person = type("M", (), {"names": {0: "person"}})()

    dets = [
        [((10, 10, 20, 20), 0.9, "person")],
        [((70, 10, 20, 20), 0.9, "person")],
        [((10, 10, 20, 20), 0.9, "person")],
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

    bboxes = [
        (10, 10, 30, 30),
        (70, 10, 90, 30),
        (10, 10, 30, 30),
    ]

    class StubDS:
        def __init__(self):
            self.i = 0

        def update_tracks(self, detections, frame=None):
            bbox = bboxes[self.i]
            self.i += 1
            return [StubTrack(bbox)]

    tracker.tracker = StubDS()
    import modules.tracker.manager as manager_mod

    monkeypatch.setattr(
        manager_mod.cv2, "imwrite", lambda path, img: True, raising=False
    )

    inf = InferWorker(tracker)
    post = PostProcessWorker(tracker)
    inf.run()
    post.run()

    assert tracker.in_counts["person"] == 1
    assert tracker.out_counts.get("person", 0) == 0


def test_detector_fps_throttles_detection(monkeypatch, tmp_path):
    r = fakeredis.FakeRedis()
    tracker = PersonTracker.__new__(PersonTracker)
    tracker.cam_id = 1
    tracker.frame_queue = queue.Queue()
    tracker.running = False
    tracker.viewers = 0
    tracker.snap_dir = Path(tmp_path)
    tracker.redis = r
    tracker.ppe_classes = []
    tracker.cfg = {}
    tracker.debug_stats = {}
    tracker.device = None
    tracker.detector_fps = 1
    tracker.groups = ["person"]
    tracker.tracks = {}
    tracker.in_counts = {}
    tracker.out_counts = {}

    frame = np.zeros((50, 50, 3), dtype=np.uint8)
    for _ in range(3):
        tracker.frame_queue.put(frame)

    detect_calls = {"n": 0}

    class Det:
        def detect(self, frame, groups):
            detect_calls["n"] += 1
            return []

    tracker.detector = Det()

    track_calls = {"n": 0}

    class StubDS:
        def update_tracks(self, detections, frame=None):
            track_calls["n"] += 1
            return []

    tracker.tracker = StubDS()

    worker = ProcessingWorker(tracker)
    worker.run()

    assert detect_calls["n"] == 1
    assert track_calls["n"] == 3
