import numpy as np

from routers import cameras


def _patch(monkeypatch):
    monkeypatch.setattr(cameras, "save_cameras", lambda *a, **k: None)
    monkeypatch.setattr(cameras, "start_tracker", lambda *a, **k: None)
    monkeypatch.setattr(cameras, "cfg", {"license_info": {"features": {}}})

    class DummyStream:
        def __init__(self, *a, **k):
            DummyStream.kwargs = k

        def wait_first_frame(self, *a, **k):
            return np.zeros((1, 1, 3), dtype=np.uint8)

        def read(self):
            return True, np.zeros((1, 1, 3), dtype=np.uint8)

        def release(self):
            pass

    class DummyCap:
        def __init__(self, *a, **k):
            pass

        def read(self):
            return True, np.zeros((1, 1, 3), dtype=np.uint8)

        def release(self):
            pass

    monkeypatch.setattr(cameras, "FFmpegCameraStream", DummyStream)
    monkeypatch.setattr(cameras, "GstCameraStream", DummyStream)
    monkeypatch.setattr(cameras.cv2, "VideoCapture", DummyCap)
    monkeypatch.setattr(cameras, "TEST_TOKENS", {})
    monkeypatch.setattr(
        cameras.cv2,
        "imencode",
        lambda ext, frame: (True, np.array([1], dtype=np.uint8)),
    )

    return DummyStream


def test_camera_add_flow(client, monkeypatch):
    DummyStream = _patch(monkeypatch)
    cameras.cams = []

    resp = client.get("/cameras/add")
    assert resp.status_code == 200

    r = client.post("/cameras/test", json={"url": "rtsp://demo"})
    assert r.status_code == 200
    assert DummyStream.kwargs["frame_skip"] == 1
    assert r.json()["notes"].startswith("/api/cameras/preview?token=")

    resp = client.post(
        "/cameras", json={"name": "Cam1", "url": "rtsp://demo", "type": "rtsp"}
    )
    assert resp.status_code == 200
    assert any(c["name"] == "Cam1" for c in cameras.cams)
