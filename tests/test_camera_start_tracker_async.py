import threading
import time

import routers.cameras as cameras


def _base_camera():
    return {
        "id": 1,
        "url": "rtsp://test",
        "type": "rtsp",
        "tasks": [],
        "ppe": False,
        "visitor_mgmt": False,
        "face_recognition": False,
        "enabled": True,
        "show": True,
        "reverse": False,
        "line_orientation": "vertical",
        "resolution": "720p",
    }


def test_add_camera_starts_tracker_async(client, monkeypatch):
    called = threading.Event()

    def fake_start_tracker(*a, **k):
        time.sleep(0.1)
        called.set()

    monkeypatch.setattr(cameras, "start_tracker", fake_start_tracker)
    monkeypatch.setattr(cameras, "save_cameras", lambda *a, **k: None)
    monkeypatch.setattr(cameras, "cams", [])
    monkeypatch.setattr(cameras, "cfg", {"enable_person_tracking": True})
    monkeypatch.setattr(cameras, "trackers_map", {})

    start = time.perf_counter()
    resp = client.post("/cameras", json={"url": "rtsp://test", "enabled": True})
    elapsed = time.perf_counter() - start
    assert resp.status_code == 200
    assert called.wait(1)
    assert elapsed < 0.2


def test_update_camera_restart_starts_tracker_async(client, monkeypatch):
    called = threading.Event()

    def fake_start_tracker(*a, **k):
        time.sleep(0.1)
        called.set()

    monkeypatch.setattr(cameras, "start_tracker", fake_start_tracker)
    monkeypatch.setattr(cameras, "save_cameras", lambda *a, **k: None)
    monkeypatch.setattr(cameras, "stop_tracker", lambda *a, **k: None)
    monkeypatch.setattr(cameras, "cfg", {"enable_person_tracking": True})
    monkeypatch.setattr(cameras, "trackers_map", {})
    monkeypatch.setattr(cameras, "cams", [_base_camera()])

    start = time.perf_counter()
    resp = client.post("/camera/1", json={})
    elapsed = time.perf_counter() - start
    assert resp.status_code == 200
    assert called.wait(1)
    assert elapsed < 0.2


def test_add_camera_disabled_does_not_start_tracker(client, monkeypatch):
    called = threading.Event()

    def fake_start_tracker(*a, **k):
        called.set()

    monkeypatch.setattr(cameras, "start_tracker", fake_start_tracker)
    monkeypatch.setattr(cameras, "save_cameras", lambda *a, **k: None)
    monkeypatch.setattr(cameras, "cams", [])
    monkeypatch.setattr(cameras, "cfg", {"enable_person_tracking": True})
    monkeypatch.setattr(cameras, "trackers_map", {})

    resp = client.post("/cameras", json={"url": "rtsp://test"})
    assert resp.status_code == 200
    assert resp.json()["camera"]["enabled"] is False
    assert not called.wait(0.2)


def test_add_camera_missing_url_returns_400(client, monkeypatch):
    monkeypatch.setattr(cameras, "cams", [])
    monkeypatch.setattr(cameras, "save_cameras", lambda *a, **k: None)
    monkeypatch.setattr(cameras, "cfg", {"enable_person_tracking": True})

    resp = client.post("/cameras", json={})
    assert resp.status_code == 400
    assert resp.json()["error"] == "Missing URL"
