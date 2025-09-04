"""Test API for camera pipeline management."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


from config import config as shared_config


def test_pipeline_crud(client):
    shared_config.setdefault("pipeline_profiles", {})["recording"] = {
        "backend": "ffmpeg"
    }
    payload = {
        "pipeline": "videoconvert",
        "url": "rtsp://example.com",
        "backend": "ffmpeg",
        "ffmpeg_flags": "-an",
        "profile": "recording",
    }
    res = client.post("/api/camera/1/pipeline", json=payload)
    assert res.status_code == 200
    assert res.json()["updated"]
    res2 = client.get("/api/camera/1/pipeline")
    assert res2.json()["pipeline"] == "videoconvert"
    assert res2.json()["profile"] == "recording"
    r = client.app.state.redis_client
    stored = r.hgetall("camera:1")
    assert stored["pipeline"] == "videoconvert"
    assert stored["url"] == "rtsp://example.com"
    assert stored["backend"] == "ffmpeg"
    assert stored["ffmpeg_flags"] == "-an"
    assert stored["profile"] == "recording"
