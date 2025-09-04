import logging

import numpy as np

from routers import cameras

logger = logging.getLogger(__name__)


class DummyStream:
    calls = []

    def __init__(self, *a, **k):
        self.last_status = "ok"
        self.last_error = ""
        DummyStream.calls.append(k)

    def wait_first_frame(self, *a, **k):
        return np.zeros((1, 1, 3), dtype=np.uint8)

    def read(self):
        return True, np.zeros((1, 1, 3), dtype=np.uint8)

    def release(self):
        pass


def test_rtsp_urls_preview(client, monkeypatch):
    monkeypatch.setattr(cameras, "FFmpegCameraStream", DummyStream)
    monkeypatch.setattr(cameras, "GstCameraStream", DummyStream)
    monkeypatch.setattr(cameras, "TEST_TOKENS", {})

    urls = [
        "rtsp://cam1.example.com/stream",
        "rtsp://cam2.example.com/stream",
    ]
    for url in urls:
        resp = client.post("/cameras/test", json={"url": url})
        assert DummyStream.calls[-1]["frame_skip"] == 1
        assert resp.status_code == 200
        assert resp.json()["notes"].startswith("/api/cameras/preview?token=")
