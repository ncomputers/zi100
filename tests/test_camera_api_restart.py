import threading
from unittest.mock import Mock

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


def test_camera_post_and_get(client, monkeypatch):
    cameras.cams = []
    monkeypatch.setattr(cameras, "save_cameras", lambda *a, **k: None)
    monkeypatch.setattr(cameras, "_start_tracker_background", lambda *a, **k: None)
    monkeypatch.setattr(
        cameras,
        "cfg",
        {"enable_person_tracking": True, "features": {}},
    )
    monkeypatch.setattr(cameras, "trackers_map", {})
    resp = client.post("/cameras", json={"url": "rtsp://test", "enabled": True})
    assert resp.status_code == 200
    resp2 = client.get("/cameras")
    assert resp2.status_code == 200


def test_put_restart_vs_refresh(client, monkeypatch):
    cam = _base_camera()
    cameras.cams = [cam]
    camera_manager = Mock()
    camera_manager.restart_capture = False
    camera_manager.update_cfg = Mock()
    cameras.trackers_map = {1: camera_manager}
    monkeypatch.setattr(cameras, "save_cameras", lambda *a, **k: None)
    monkeypatch.setattr(
        cameras, "cfg", {"enable_person_tracking": True, "features": {}}
    )

    resp = client.put("/cameras/1", json={"url": "rtsp://new"})
    assert resp.status_code == 200
    assert camera_manager.restart_capture is True

    camera_manager.restart_capture = False
    camera_manager.update_cfg.reset_mock()
    resp = client.put("/cameras/1", json={"show": False})
    assert resp.status_code == 200
    assert camera_manager.restart_capture is False
    assert camera_manager.update_cfg.called


def test_put_invalid_id_returns_422(client):
    resp = client.put("/cameras/notanid", json={})
    assert resp.status_code == 422
    assert isinstance(resp.json().get("detail"), list)
