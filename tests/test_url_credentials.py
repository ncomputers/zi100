"""Test URL credential normalization across streams."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from modules.ffmpeg_stream import FFmpegCameraStream
from modules.gstreamer_stream import GstCameraStream
from utils.url import normalize_stream_url


def test_normalize_stream_url_encodes_credentials():
    url = "rtsp://user name:p@ss@example.com/stream"
    expected = "rtsp://user%20name:p%40ss@example.com/stream"
    assert normalize_stream_url(url) == expected


class DummyVideoCapture:
    def __init__(self, src):
        self.src = src

    def read(self):
        return False, None

    def release(self):
        pass

    def set(self, *args, **kwargs):
        pass


def test_stream_classes_use_normalized_url(monkeypatch):
    url = "rtsp://user%40name:p%23ss@example.com/stream"

    # Dummy video capture to avoid real OpenCV IO
    import cv2

    monkeypatch.setattr(cv2, "VideoCapture", DummyVideoCapture, raising=False)
    monkeypatch.setattr(FFmpegCameraStream, "_start_process", lambda self: None)

    ff = FFmpegCameraStream(url, width=1, height=1, start_thread=False)
    assert ff.url == url
    ff.release()

    gst = GstCameraStream(url, width=1, height=1, start_thread=False)
    assert f'location="{url}"' in gst.pipeline
    gst.release()
