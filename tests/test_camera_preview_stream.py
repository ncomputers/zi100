import io
import subprocess
import time

import numpy as np

from routers import cameras


def _patch(monkeypatch):
    monkeypatch.setattr(cameras, "cfg", {})
    monkeypatch.setattr(cameras, "TEST_STREAMS", {})
    monkeypatch.setattr(cameras, "TEST_CAMERA_PROBES", {})
    monkeypatch.setattr(cameras, "TEST_TOKENS", {})

    class DummyStream:
        def __init__(self, *a, **k):
            DummyStream.kwargs = k
            if a:
                DummyStream.kwargs["url"] = a[0]

        def wait_first_frame(self, *a, **k):
            return np.zeros((1, 1, 3), dtype=np.uint8)

        def read(self, *a, **k):

            return True, np.zeros((1, 1, 3), dtype=np.uint8)

        def release(self):
            pass

    monkeypatch.setattr(cameras, "FFmpegCameraStream", DummyStream)
    monkeypatch.setattr(cameras, "GstCameraStream", DummyStream)
    return DummyStream


def _patch_fail(monkeypatch):
    monkeypatch.setattr(cameras, "cfg", {})
    monkeypatch.setattr(cameras, "TEST_STREAMS", {})
    monkeypatch.setattr(cameras, "TEST_CAMERA_PROBES", {})
    monkeypatch.setattr(cameras, "TEST_TOKENS", {})

    class FailStream:
        def __init__(self, *a, **k):
            self.last_status = "error"
            self.last_error = "boom"
            self.last_stderr = "fail"

        def read(self):
            return False, None

        def release(self):
            pass

    monkeypatch.setattr(cameras, "FFmpegCameraStream", FailStream)
    monkeypatch.setattr(cameras, "GstCameraStream", FailStream)
    return FailStream


def test_camera_preview_stream(client, monkeypatch):
    DummyStream = _patch(monkeypatch)
    r = client.post("/cameras/test", json={"url": "rtsp://demo", "stream": True})
    assert r.status_code == 200
    assert DummyStream.kwargs["frame_skip"] == 1
    assert DummyStream.kwargs["test"] is True
    assert DummyStream.kwargs["url"] == "rtsp://demo?subtype=1"
    assert DummyStream.kwargs.get("downscale") is None
    notes = r.json()["notes"]
    assert notes.startswith("/api/cameras/preview?token=")


def test_camera_preview_stream_downscale(client, monkeypatch):
    DummyStream = _patch(monkeypatch)
    r = client.post("/cameras/test", json={"url": "rtsp://demo", "downscale": 2})
    assert r.status_code == 200
    assert DummyStream.kwargs["downscale"] == 2
    assert DummyStream.kwargs["test"] is True
    assert DummyStream.kwargs["url"] == "rtsp://demo?subtype=1"
    notes = r.json()["notes"]
    assert notes.startswith("/api/cameras/preview?token=")


def test_camera_preview_stream_error(client, monkeypatch):
    monkeypatch.setattr(cameras, "cfg", {})
    monkeypatch.setattr(cameras, "TEST_CAMERA_TRANSPORT", {})

    class FailStream:
        def __init__(self, *a, **k):
            self.last_status = "network"
            self.last_error = "netfail"
            self.last_stderr = "err\nrtsp://u:p@demo\nmore"
            self.last_command = "ffmpeg -i rtsp://u:p@demo"

        def read(self):
            return False, None

        def release(self):
            pass

    monkeypatch.setattr(cameras, "FFmpegCameraStream", FailStream)
    monkeypatch.setattr(cameras, "GstCameraStream", FailStream)

    r = client.post("/cameras/test", json={"url": "rtsp://demo"})
    assert r.status_code == 400
    data = r.json()
    assert data["error"] == "netfail"
    assert "***:***@" in data.get("ffmpeg_cmd", "")
    assert "more" in data.get("stderr_tail", "")
    assert data.get("transports") == ["tcp", "udp"]
    assert "suggestion" in data


def test_preview_endpoint(client, monkeypatch):
    DummyStream = _patch(monkeypatch)
    r = client.post("/cameras/test", json={"url": "rtsp://demo"})
    token_url = r.json()["notes"]

    class DummyProc:
        def __init__(self, cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE):
            self.cmd = cmd
            self.stdout = io.BytesIO(b"--frame\r\n")
            self.stderr = io.BytesIO(b"err")

        def poll(self):
            return 0

        def kill(self):
            pass

    monkeypatch.setattr(cameras.subprocess, "Popen", DummyProc)
    resp = client.get(token_url)
    assert resp.status_code == 200
    assert b"--frame" in resp.content


def test_preview_limit(client, monkeypatch):
    _patch(monkeypatch)
    cameras.TEST_STREAMS = {"a": object(), "b": object(), "c": object()}
    token = "tok"
    cameras.TEST_TOKENS[token] = {
        "url": "rtsp://demo",
        "transport": "tcp",
        "expires": time.monotonic() + 60,
    }
    resp = client.get(f"/api/cameras/preview?token={token}")
    assert resp.status_code == 429
    assert resp.json()["error"] == "Please close other previews"
