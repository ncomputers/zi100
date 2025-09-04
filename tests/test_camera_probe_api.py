import types

from fastapi.testclient import TestClient

from modules import stream_probe


def test_camera_probe_endpoint(client: TestClient, monkeypatch):
    def fake_probe(url, sample_seconds=8, enable_hwaccel=True):
        return {
            "metadata": {"codec": "h264", "width": 640, "height": 480},
            "transport": "tcp",
            "hwaccel": False,
            "effective_fps": 29.7,
        }

    monkeypatch.setattr(stream_probe, "probe_stream", fake_probe)
    body = {
        "name": "cam1",
        "type": "RTSP",
        "url": "rtsp://example",
        "transport": "TCP",
        "timeout_sec": 8,
    }
    resp = client.post("/cameras/probe", json=body)
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    assert data["details"]["codec"] == "h264"
    assert data["details"]["resolution"] == "640x480"
    assert data["details"]["transport_used"] == "tcp"


def test_camera_probe_bad_url(client: TestClient):
    body = {
        "name": "cam1",
        "type": "RTSP",
        "url": "http://example",  # not rtsp
        "transport": "TCP",
        "timeout_sec": 5,
    }
    resp = client.post("/cameras/probe", json=body)
    assert resp.status_code == 400
    data = resp.json()
    assert data["ok"] is False
    assert data["error_code"] == "BAD_URL"
