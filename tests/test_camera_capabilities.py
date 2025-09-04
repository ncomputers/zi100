import numpy as np
from routers import cameras


def _patch(monkeypatch):
    monkeypatch.setattr(
        cameras,
        "cfg",
        {"license_info": {"features": {"ppe_detection": True, "visitor_mgmt": False, "face_recognition": True, "in_out_counting": True}}},
    )

    class DummyCap:
        def __init__(self, *a, **k):
            pass

        def read(self):
            return True, np.zeros((720, 1280, 3), dtype=np.uint8)

        def get(self, prop):
            if prop == cameras.cv2.CAP_PROP_FRAME_WIDTH:
                return 1280
            if prop == cameras.cv2.CAP_PROP_FRAME_HEIGHT:
                return 720
            if prop == cameras.cv2.CAP_PROP_FPS:
                return 30
            return 0

        def release(self):
            pass

    monkeypatch.setattr(cameras.cv2, "VideoCapture", DummyCap)


def test_camera_capabilities(client, monkeypatch):
    _patch(monkeypatch)
    r = client.post("/cameras/capabilities", json={"url": "0"})
    assert r.status_code == 200
    data = r.json()
    assert data["resolution"] == {"width": 1280, "height": 720}
    assert data["fps"] == 30
    assert data["license"]["ppe_detection"] is True
    assert data["license"]["visitor_mgmt"] is False
