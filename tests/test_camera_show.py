import routers.cameras as cameras


def _patch(monkeypatch):
    monkeypatch.setattr(cameras, "save_cameras", lambda *a, **k: None)
    monkeypatch.setattr(cameras, "start_tracker", lambda *a, **k: None)
    monkeypatch.setattr(cameras, "cfg", {})
    monkeypatch.setattr(cameras, "trackers_map", {})


def test_add_camera_show_defaults_false(client, monkeypatch):
    _patch(monkeypatch)
    cameras.cams = []
    resp = client.post("/cameras", json={"url": "rtsp://test"})
    assert resp.status_code == 200
    assert resp.json()["camera"]["show"] is False


def test_add_camera_respects_show_field(client, monkeypatch):
    _patch(monkeypatch)
    cameras.cams = []
    resp = client.post("/cameras", json={"url": "rtsp://test", "show": True})
    assert resp.status_code == 200
    assert resp.json()["camera"]["show"] is True


def test_toggle_show_uses_stored_value(client, monkeypatch):
    _patch(monkeypatch)
    cameras.cams = [{
        "id": 1,
        "url": "rtsp://test",
        "type": "rtsp",
        "tasks": [],
        "ppe": False,
        "visitor_mgmt": False,
        "face_recognition": False,
        "enable_face_counting": False,
        "enabled": True,
        "show": False,
        "reverse": False,
        "line_orientation": "vertical",
        "resolution": "720p",
    }]
    resp = client.patch("/cameras/1/show")
    assert resp.status_code == 200
    assert cameras.cams[0]["show"] is True
    assert resp.json()["show"] is True
