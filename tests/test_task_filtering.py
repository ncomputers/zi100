import fakeredis

import core.tracker_manager as tm


def test_full_monitor_retained_when_ppe_disabled(monkeypatch):
    captured = {}

    class DummyWorker:
        def run(self):
            pass

    class DummyTracker:
        def __init__(self, cam_id, url, obj_classes, cfg, tasks, cam_type, **kwargs):
            captured["tasks"] = tasks
            self.capture_worker = DummyWorker()
            self.infer_worker = DummyWorker()
            self.post_worker = DummyWorker()

    monkeypatch.setattr(tm, "PersonTracker", DummyTracker)

    class DummyThread:
        def __init__(self, target, daemon=True):
            self.target = target

        def start(self):
            self.target()

    monkeypatch.setattr(tm.threading, "Thread", DummyThread)

    r = fakeredis.FakeRedis()
    cam = {"id": 1, "url": "rtsp://", "tasks": ["full_monitor", "helmet"]}
    cfg = {"license_info": {"features": {"ppe_detection": False}}}
    trackers = {}

    tm.start_tracker(cam, cfg, trackers, r)

    assert captured["tasks"] == ["full_monitor"]
