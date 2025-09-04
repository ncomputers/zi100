"""Tests for media health endpoint."""

import app as app_module


def test_health_media_endpoint(client, monkeypatch):
    class DummyTracker:
        def __init__(self):
            self.capture_backend = "gstreamer"

    client.app.state.trackers = {1: DummyTracker()}
    client.app.state.redis_client.set("camera_debug:1", "fail")
    monkeypatch.setattr(
        app_module, "get_tracker_status", lambda: {1: {"process_alive": True}}
    )
    resp = client.get("/health/media")
    assert resp.status_code == 200
    data = resp.json()
    assert data["1"]["backend"] == "gstreamer"
    assert data["1"]["process_alive"] is True
    assert data["1"]["last_error"] == "fail"
