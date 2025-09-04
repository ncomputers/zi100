import json
from datetime import date

import fakeredis
import redis

import core.tracker_manager as tm
from core import stats
from core.config import (
    _sanitize_track_ppe,
    sync_detection_classes,
    load_branding,
    save_branding,
)


class DummyTracker:
    def __init__(self):
        self.in_counts = {"person": 1}
        self.out_counts = {"person": 0}
        self.in_count = 1
        self.out_count = 0
        self.tracks = set([1])
        self.prev_date = date.today()
        self.redis = fakeredis.FakeRedis()
        self.key_in = "in"
        self.key_out = "out"
        self.key_date = "date"
        self.capture_loop = lambda: None
        self.infer_loop = lambda: None
        self.post_process_loop = lambda: None


def test_gather_stats():
    r = fakeredis.FakeRedis()
    for item in stats.ANOMALY_ITEMS:
        r.set(f"{item}_count", 1)
    tr = DummyTracker()
    data = stats.gather_stats({1: tr}, r)
    assert data["in_count"] == 1
    assert data["anomaly_counts"][stats.ANOMALY_ITEMS[0]] == 1


def test_broadcast_stats(monkeypatch):
    r = fakeredis.FakeRedis()
    tr = DummyTracker()
    published = {}

    def fake_publish(ch, msg):
        published["channel"] = ch
        published["msg"] = json.loads(msg)

    monkeypatch.setattr(r, "publish", fake_publish)
    stats.broadcast_stats({1: tr}, r)
    assert published["channel"] == "stats_updates"
    assert "in_count" in published["msg"]


def test_normalize_tasks():
    assert tm.normalize_tasks(None) == ["in_count", "out_count"]
    assert tm.normalize_tasks({"counting": {"in": True}, "ppe": ["helmet"]}) == [
        "in_count",
        "helmet",
    ]


def test_load_and_save_cameras():
    r = fakeredis.FakeRedis()
    cams = [{"id": 1, "url": "rtsp://", "tasks": {"counting": {"in": True}}}]
    tm.save_cameras(cams, r)
    loaded = tm.load_cameras(r, "")
    assert loaded[0]["tasks"] == ["in_count"]


def test_reset_counts():
    tr = DummyTracker()
    tm.reset_counts({1: tr})
    assert tr.in_count == 0 and tr.out_count == 0
    assert tr.redis.get("in") == b"0"


def test_log_counts(monkeypatch):
    r = fakeredis.FakeRedis()
    tr = DummyTracker()
    called = {}

    def fake_broadcast(trackers, r):
        called["ok"] = True

    monkeypatch.setattr(stats, "broadcast_stats", fake_broadcast)
    tm.log_counts(r, {1: tr})
    assert called["ok"]
    assert r.zcard("history") == 1


def test_sanitize_track_ppe():
    assert _sanitize_track_ppe(["No Helmet", "helmet"]) == ["helmet"]


def test_sync_detection_classes():
    cfg = {"track_objects": ["person"], "track_ppe": ["helmet"]}
    sync_detection_classes(cfg)
    assert "ppe_classes" in cfg and "helmet" in cfg["ppe_classes"]


def test_load_branding_defaults(tmp_path):
    path = tmp_path / "branding.json"
    data = load_branding(str(path))
    assert data["company_name"]


def test_save_branding(tmp_path):
    path = tmp_path / "branding.json"
    save_branding({"company_name": "X"}, str(path))
    with open(path) as f:
        saved = json.load(f)
    assert saved["company_name"] == "X"


def test_reset_backoff():
    tr = DummyTracker()
    tm.tracker_threads[1] = {"restart_attempts": 3}
    tm.reset_backoff(1)
    assert tm.tracker_threads[1]["restart_attempts"] == 0
    tm.tracker_threads.clear()
