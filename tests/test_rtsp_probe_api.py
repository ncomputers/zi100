import shutil

from fastapi.testclient import TestClient

from modules import stream_probe


def test_rtsp_probe_endpoint(client: TestClient, monkeypatch):
    def fake_probe(url, sample_seconds=6, enable_hwaccel=True):
        return {
            "metadata": {
                "codec": "h264",
                "profile": "Main",
                "width": 1280,
                "height": 720,
                "pix_fmt": "yuv420p",
                "bit_rate": None,
                "avg_frame_rate": "20/1",
                "r_frame_rate": "20/1",
                "nominal_fps": 20.0,
            },
            "transport": "TCP",
            "hwaccel": True,
            "frames": 157,
            "effective_fps": 19.6,
            "elapsed": 8.02,
        }

    monkeypatch.setattr(stream_probe, "probe_stream", fake_probe)
    monkeypatch.setattr(shutil, "which", lambda name: "/usr/bin/" + name)

    payload = {
        "url": "rtsp://admin:pass@192.168.31.11:554/cam/realmonitor?channel=1&subtype=1"
    }
    resp = client.post("/api/rtsp/probe", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    assert data["parsed"]["host"] == "192.168.31.11"
    assert data["meta"]["width"] == 1280
    assert data["measure"]["transport_used"] == "TCP"
