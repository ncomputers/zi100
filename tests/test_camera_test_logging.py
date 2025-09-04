from loguru import logger

from routers import cameras


def test_camera_test_logs_masked_credentials(client, monkeypatch):
    monkeypatch.setattr(cameras, "cfg", {})
    monkeypatch.setattr(cameras, "TEST_CAMERA_TRANSPORT", {})
    monkeypatch.setattr(cameras, "TEST_TOKENS", {})

    class FailStream:
        def __init__(self, *a, **k):
            self.last_status = "network"
            self.last_error = "netfail"
            self.last_stderr = "err\nrtsp://user:pass@demo\nmore"
            self.last_command = "ffmpeg -i rtsp://user:pass@demo"

        def read(self):
            return False, None

        def release(self):
            pass

    monkeypatch.setattr(cameras, "FFmpegCameraStream", FailStream)
    monkeypatch.setattr(cameras, "GstCameraStream", FailStream)

    logs = []
    handle = logger.add(lambda m: logs.append(m), level="DEBUG")
    try:
        r = client.post("/cameras/test", json={"url": "rtsp://demo"})
    finally:
        logger.remove(handle)
    assert r.status_code == 400
    joined = "".join(logs)
    assert "***:***@" in joined
    assert "user:pass@" not in joined
    assert "more" in joined
