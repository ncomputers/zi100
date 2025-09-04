"""Purpose: Test buffer seconds module."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import types


# DummyCap class encapsulates dummycap behavior
class DummyCap:
    # isOpened routine
    def isOpened(self):
        return True


sys.modules["cv2"] = types.SimpleNamespace(
    CAP_GSTREAMER=0, VideoCapture=lambda *a, **k: DummyCap()
)
import importlib

import modules.gstreamer_stream as gst_mod

importlib.reload(gst_mod)

from modules.ffmpeg_stream import FFmpegCameraStream
from modules.gstreamer_stream import GstCameraStream


# Test gst pipeline drops old frames
def test_gst_pipeline_simple():
    stream = GstCameraStream("rtsp://x", buffer_seconds=10, start_thread=False)
    assert "latency=100" in stream.pipeline
    assert "avdec_h264" in stream.pipeline
    assert "queue max-size-buffers=1" in stream.pipeline
    assert "drop=true" in stream.pipeline


# DummyPopen class encapsulates dummypopen behavior
class DummyPopen:
    # __init__ routine
    def __init__(self, *a, **k):
        pass

    # poll routine
    def poll(self):
        return None

    # kill routine
    def kill(self):
        pass

    @property
    # stdout routine
    def stdout(self):
        import io

        return io.BytesIO(b"\x00" * 4)


# Test ffmpeg cmd has rtbuf
def test_ffmpeg_cmd_simple(monkeypatch):
    called = []

    # fake_popen routine
    def fake_popen(cmd, stdin=None, stdout=None, stderr=None, bufsize=None, **kwargs):
        called.extend(cmd)
        return DummyPopen()

    import subprocess

    monkeypatch.setattr(subprocess, "Popen", fake_popen)
    FFmpegCameraStream("rtsp://y", width=2, height=2, start_thread=False)
    assert called[0] == "ffmpeg"
    assert "-rtsp_transport" in called
