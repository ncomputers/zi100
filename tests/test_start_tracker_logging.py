import threading
import time

from loguru import logger

import routers.cameras as cameras


def test_slow_start_logs_warning(client, monkeypatch):
    called = threading.Event()
    messages = []

    def sink(message):
        messages.append(message)

    handler_id = logger.add(sink, level="WARNING")

    def slow_start(*a, **k):
        time.sleep(0.1)
        called.set()

    monkeypatch.setattr(cameras, "start_tracker", slow_start)
    monkeypatch.setattr(cameras, "save_cameras", lambda *a, **k: None)
    monkeypatch.setattr(cameras, "cams", [])
    monkeypatch.setattr(cameras, "cfg", {"enable_person_tracking": True})
    monkeypatch.setattr(cameras, "trackers_map", {})
    monkeypatch.setattr(cameras, "START_TRACKER_WARN_AFTER", 0.01)

    resp = client.post("/cameras", json={"url": "rtsp://test"})
    assert resp.status_code == 200
    called.wait(1)
    time.sleep(0.05)

    logger.remove(handler_id)
    assert any("start_tracker took" in str(m) for m in messages)
