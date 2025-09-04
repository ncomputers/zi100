import asyncio
import numpy as np
from loguru import logger
from routers import cameras


class DummyRequest:
    def __init__(self, data):
        self._data = data

    async def json(self):
        return self._data

    async def is_disconnected(self):
        return False


def test_camera_logs_selected_transport(monkeypatch):
    monkeypatch.setattr(cameras, "cfg", {}, raising=False)
    monkeypatch.setattr(cameras, "TEST_CAMERA_TRANSPORT", {})
    monkeypatch.setattr(cameras, "TEST_CAMERA_PROBES", {})

    class DummyStream:
        def __init__(self, *a, **k):
            self.last_status = "ok"
            self.last_error = ""
            self.last_hint = ""
            self.last_stderr = ""
            self.last_command = ""

        def read(self):
            return True, np.zeros((1, 1, 3), dtype=np.uint8)

        def wait_first_frame(self):
            return np.zeros((1, 1, 3), dtype=np.uint8)

        def release(self):
            pass

    monkeypatch.setattr(cameras, "FFmpegCameraStream", DummyStream)
    monkeypatch.setattr(cameras, "GstCameraStream", DummyStream)
    monkeypatch.setattr(
        cameras.cv2,
        "imencode",
        lambda ext, frame: (True, np.array([1], dtype=np.uint8)),
    )

    logs = []
    handle = logger.add(lambda m: logs.append(m), level="INFO")
    try:
        req = DummyRequest({"url": "rtsp://demo"})
        resp = asyncio.run(cameras.test_camera(req))
    finally:
        logger.remove(handle)
    assert resp.status_code == 200
    joined = "".join(logs)
    assert "[test_camera] using TCP transport" in joined
    assert "'transport': 'tcp'" in joined
