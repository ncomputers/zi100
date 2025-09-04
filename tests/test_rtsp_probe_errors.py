import shutil

import pytest
from fastapi.testclient import TestClient

from modules import stream_probe


@pytest.mark.parametrize(
    "error_msg",
    [
        "401 Unauthorized",
        "No route to host",
        "Connection timed out",
        "Unsupported codec",
    ],
)
def test_rtsp_probe_error_codes(
    client: TestClient, monkeypatch, error_msg: str
) -> None:
    def fake_probe(url, sample_seconds=6, enable_hwaccel=True):
        raise RuntimeError(error_msg)

    monkeypatch.setattr(stream_probe, "probe_stream", fake_probe)
    monkeypatch.setattr(shutil, "which", lambda name: "/usr/bin/" + name)
    resp = client.post("/api/rtsp/probe", json={"url": "rtsp://example"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is False
    assert error_msg in data["error"]


def test_rtsp_probe_ffmpeg_not_found(client: TestClient, monkeypatch) -> None:
    monkeypatch.setattr(shutil, "which", lambda name: None)
    resp = client.post("/api/rtsp/probe", json={"url": "rtsp://example"})
    assert resp.status_code == 200
    assert resp.json() == {"ok": False, "error": "ffmpeg/ffprobe not found"}
