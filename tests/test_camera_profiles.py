from app import _load_camera_profiles


def test_load_camera_profiles_missing_stream_url(monkeypatch):
    captured = {}

    def fake_load_cameras(redis_client, default_url):
        captured["default_url"] = default_url
        return []

    monkeypatch.setattr("app.load_cameras", fake_load_cameras)

    cams = _load_camera_profiles(object(), {}, None)

    assert captured["default_url"] == ""
    assert cams == []


def test_load_camera_profiles_uses_config_stream_url(monkeypatch):
    captured = {}

    def fake_load_cameras(redis_client, default_url):
        captured["default_url"] = default_url
        return []

    monkeypatch.setattr("app.load_cameras", fake_load_cameras)

    _load_camera_profiles(object(), {"stream_url": "rtsp://cam"}, None)

    assert captured["default_url"] == "rtsp://cam"
