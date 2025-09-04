"""Tests for tracker watchdog and health endpoint."""

import sys
import threading
import time
import types

from core import tracker_manager

# ensure cv2 has required attribute
sys.modules["cv2"] = types.SimpleNamespace(setNumThreads=lambda n: None)


class DummyTracker:
    def __init__(self):
        self.running = True
        self._cap_failed = False
        self._proc_failed = False

    def capture_loop(self):
        if not self._cap_failed:
            self._cap_failed = True
            return
        while self.running:
            time.sleep(0.1)

    def process_loop(self):
        if not self._proc_failed:
            self._proc_failed = True
            return
        while self.running:
            time.sleep(0.1)


def test_watchdog_restarts_threads(monkeypatch):
    """Watchdog should restart dead threads with backoff."""
    monkeypatch.setattr(tracker_manager, "BACKOFF_BASE", 0.01)
    tr = DummyTracker()
    trackers = {1: tr}
    # start failing threads
    t1 = threading.Thread(target=tr.capture_loop)
    t2 = threading.Thread(target=tr.process_loop)
    t1.start()
    t2.start()
    t1.join()
    t2.join()
    tracker_manager.tracker_threads[1] = {
        "capture": t1,
        "process": t2,
        "restart_attempts": 0,
        "timer": None,
    }
    tracker_manager.watchdog_tick(trackers)
    time.sleep(0.05)
    status = tracker_manager.get_tracker_status()
    assert status[1]["restart_attempts"] == 1
    assert status[1]["capture_alive"]
    assert status[1]["process_alive"]
    tr.running = False
    tracker_manager.stop_tracker(1, trackers)


def test_health_trackers_endpoint(client):
    resp = client.get("/health/trackers")
    assert resp.status_code == 200
    assert isinstance(resp.json(), dict)
