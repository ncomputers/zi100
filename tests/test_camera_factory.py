"""Purpose: Test camera factory module."""

import io
import json
import subprocess
import sys
import time
import types
from pathlib import Path

import fakeredis
import numpy as np
import pytest

ffmpeg = types.SimpleNamespace(probe=lambda *a, **k: {})

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import modules.camera_factory as cf
from config import config as shared_config
from modules.base_camera import BaseCameraStream


@pytest.fixture(autouse=True)
def _patch_resolution(monkeypatch):
    monkeypatch.setattr(cf, "get_stream_resolution", lambda url: (640, 480))


# DummyGst class encapsulates dummygst behavior
class DummyGst(BaseCameraStream):
    # __init__ routine
    def __init__(self, *args, **kwargs):
        self.pipeline = kwargs.get("pipeline")
        super().__init__(kwargs.get("buffer_size", 3))

    # _init_stream routine
    def _init_stream(self):
        pass

    # _read_frame routine
    def _read_frame(self):
        return True, np.zeros((1, 1, 3), dtype=np.uint8)

    def read_latest(self):
        return True, np.zeros((1, 1, 3), dtype=np.uint8)

    # _release_stream routine
    def _release_stream(self):
        pass


# DummyFFmpeg class encapsulates dummyffmpeg behavior
class DummyFFmpeg(BaseCameraStream):
    # __init__ routine
    def __init__(self, *args, **kwargs):
        self.extra_flags = kwargs.get("extra_flags")
        self.transport = kwargs.get("transport")
        super().__init__(kwargs.get("buffer_size", 3))

    # _init_stream routine
    def _init_stream(self):
        pass

    # _read_frame routine
    def _read_frame(self):
        return True, np.zeros((1, 1, 3), dtype=np.uint8)

    def read_latest(self):
        return True, np.zeros((1, 1, 3), dtype=np.uint8)

    # _release_stream routine
    def _release_stream(self):
        pass


# Test open capture fallback
def test_open_capture_fallback(monkeypatch):
    monkeypatch.setattr(cf, "GstCameraStream", DummyGst)
    monkeypatch.setattr(cf, "FFmpegCameraStream", DummyFFmpeg)
    cap, _ = cf.open_capture(
        "rtsp://test", 1, src_type="rtsp", backend_priority=["gstreamer", "ffmpeg"]
    )
    assert isinstance(cap, DummyFFmpeg)
    cap.release()


def test_open_capture_custom_resolution(monkeypatch):
    monkeypatch.setitem(shared_config, "enable_gstreamer", True)
    monkeypatch.setattr(
        cf,
        "get_stream_resolution",
        lambda url: (_ for _ in ()).throw(AssertionError("called")),
    )

    class SizeGst(BaseCameraStream):
        def __init__(self, src, width, height, *args, **kwargs):
            self.size = (width, height)
            self.pipeline = kwargs.get("pipeline")
            super().__init__(kwargs.get("buffer_size", 3))

        def _init_stream(self):
            pass

        def _read_frame(self):
            return True, np.zeros((1, 1, 3), dtype=np.uint8)

        def read_latest(self):
            return True, np.zeros((1, 1, 3), dtype=np.uint8)

        def _release_stream(self):
            pass

    monkeypatch.setattr(cf, "GstCameraStream", SizeGst)
    monkeypatch.setattr(cf, "FFmpegCameraStream", DummyFFmpeg)
    cap, _ = cf.open_capture(
        "rtsp://t",
        1,
        src_type="rtsp",
        resolution="123x456",
        backend_priority=["gstreamer"],
    )
    assert isinstance(cap, SizeGst)
    assert cap.size == (123, 456)
    cap.release()


def test_backend_priority_skips_disabled(monkeypatch):
    monkeypatch.setattr(cf, "GstCameraStream", DummyGst)
    monkeypatch.setattr(cf, "FFmpegCameraStream", DummyFFmpeg)
    from config import config as shared_config

    monkeypatch.setitem(shared_config, "enable_gstreamer", False)
    cap, _ = cf.open_capture(
        "rtsp://test", 1, src_type="rtsp", backend_priority=["gstreamer", "ffmpeg"]
    )
    assert isinstance(cap, DummyFFmpeg)
    cap.release()


def test_default_priority_skips_gstreamer(monkeypatch):
    calls = {"gst": 0}

    class FailGst(BaseCameraStream):
        def __init__(self, *a, **k):
            calls["gst"] += 1
            raise AssertionError("should not be called")

    class DummyFF(BaseCameraStream):
        def __init__(self, *a, **k):
            self.transport = k.get("transport")
            super().__init__(k.get("buffer_size", 3))

        def _init_stream(self):
            pass

        def _read_frame(self):
            return True, np.zeros((1, 1, 3), dtype=np.uint8)

        def read_latest(self):
            return True, np.zeros((1, 1, 3), dtype=np.uint8)

        def _release_stream(self):
            pass

    monkeypatch.setitem(shared_config, "enable_gstreamer", False)
    monkeypatch.setattr(cf, "GstCameraStream", FailGst)
    monkeypatch.setattr(cf, "FFmpegCameraStream", DummyFF)
    cap, _ = cf.open_capture(
        "rtsp://t",
        1,
        src_type="rtsp",
        backend_priority=None,
        ready_frames=1,
        for_display=True,
    )

    assert isinstance(cap, DummyFF)
    assert calls["gst"] == 0
    cap.release()


def test_fallback_all_backends(monkeypatch):
    monkeypatch.setitem(shared_config, "enable_gstreamer", True)

    class FailGst(BaseCameraStream):
        def __init__(self, *a, **k):
            raise cf.StreamUnavailable("gst fail")

    class FailFF(BaseCameraStream):
        def __init__(self, *a, **k):
            raise cf.StreamUnavailable("ff fail")

    class DummyCV(BaseCameraStream):
        def __init__(self, *a, **k):
            super().__init__(k.get("buffer_size", 3))

        def _init_stream(self):
            pass

        def _read_frame(self):
            return True, np.zeros((1, 1, 3), dtype=np.uint8)

        def read_latest(self):
            return True, np.zeros((1, 1, 3), dtype=np.uint8)

        def _release_stream(self):
            pass

    monkeypatch.setattr(cf, "GstCameraStream", FailGst)
    monkeypatch.setattr(cf, "FFmpegCameraStream", FailFF)
    monkeypatch.setattr(cf, "OpenCVCameraStream", DummyCV)

    cap, _ = cf.open_capture(
        "rtsp://t",
        1,
        src_type="rtsp",
        backend_priority=None,
        ready_frames=1,
        for_display=True,
    )

    assert isinstance(cap, DummyCV)
    cap.release()


def test_fallback_without_gstreamer(monkeypatch):
    monkeypatch.setitem(shared_config, "enable_gstreamer", False)

    calls = {"gst": 0}

    class FailGst(BaseCameraStream):
        def __init__(self, *a, **k):
            calls["gst"] += 1
            raise cf.StreamUnavailable("gst fail")

    class FailFF(BaseCameraStream):
        def __init__(self, *a, **k):
            raise cf.StreamUnavailable("ff fail")

    class DummyCV(BaseCameraStream):
        def __init__(self, *a, **k):
            super().__init__(k.get("buffer_size", 3))

        def _init_stream(self):
            pass

        def _read_frame(self):
            return True, np.zeros((1, 1, 3), dtype=np.uint8)

        def read_latest(self):
            return True, np.zeros((1, 1, 3), dtype=np.uint8)

        def _release_stream(self):
            pass

    monkeypatch.setattr(cf, "GstCameraStream", FailGst)
    monkeypatch.setattr(cf, "FFmpegCameraStream", FailFF)
    monkeypatch.setattr(cf, "OpenCVCameraStream", DummyCV)

    cap, _ = cf.open_capture(
        "rtsp://t",
        1,
        src_type="rtsp",
        backend_priority=None,
        ready_frames=1,
        for_display=True,
    )

    assert isinstance(cap, DummyCV)
    assert calls["gst"] == 0
    cap.release()


def test_gstreamer_failure_records_debug(monkeypatch):
    import fakeredis

    from config import config as shared_config

    class ErrGst(BaseCameraStream):
        def __init__(self, *a, **k):
            raise RuntimeError("boom")

    class DummyFFmpeg(BaseCameraStream):
        def __init__(self, *args, **kwargs):
            self.transport = kwargs.get("transport")
            super().__init__(kwargs.get("buffer_size", 3))

        def _init_stream(self):
            pass

        def _read_frame(self):
            return True, np.zeros((1, 1, 3), dtype=np.uint8)

        def _release_stream(self):
            pass

    fake_r = fakeredis.FakeRedis(decode_responses=True)
    cf.redis_client = fake_r
    monkeypatch.setitem(shared_config, "enable_gstreamer", True)
    monkeypatch.setattr(cf, "GstCameraStream", ErrGst)
    monkeypatch.setattr(cf, "FFmpegCameraStream", DummyFFmpeg)

    cap, _ = cf.open_capture(
        "rtsp://test", 1, src_type="rtsp", backend_priority=["gstreamer", "ffmpeg"]
    )
    assert isinstance(cap, DummyFFmpeg)
    data = json.loads(fake_r.get("camera_debug:1"))
    assert any("GStreamer" in a["error"] for a in data["attempts"])
    cap.release()
    cf.redis_client = None


def test_ready_duration(monkeypatch):
    monkeypatch.setattr(cf, "GstCameraStream", DummyGst)
    from config import config as shared_config

    monkeypatch.setitem(shared_config, "enable_gstreamer", True)
    cap, _ = cf.open_capture(
        "rtsp://test",
        1,
        src_type="rtsp",
        backend_priority=["gstreamer"],
        ready_frames=0,
        ready_duration=0.2,
        ready_timeout=1.0,
    )
    assert isinstance(cap, DummyGst)
    cap.release()


def test_open_capture_uses_probe(monkeypatch):
    import fakeredis

    summary = {
        "metadata": {"codec": "h264", "width": 640, "height": 480, "fps": 30},
        "transport": "udp",
        "hwaccel": True,
        "frames": 100,
        "effective_fps": 50.0,
        "trials": [],
    }

    called: dict[str, str] = {}

    class DummyFF(BaseCameraStream):
        def __init__(self, *a, transport, **k):
            called["transport"] = transport
            self.transport = transport
            super().__init__(k.get("buffer_size", 3))

        def _init_stream(self):
            pass

        def _read_frame(self):
            return True, np.zeros((1, 1, 3), dtype=np.uint8)

        def read_latest(self):
            return True, np.zeros((1, 1, 3), dtype=np.uint8)

        def _release_stream(self):
            pass

    fake_r = fakeredis.FakeRedis(decode_responses=True)
    cf.redis_client = fake_r
    monkeypatch.setattr(cf, "probe_stream", lambda *a, **k: summary)
    monkeypatch.setattr(cf, "FFmpegCameraStream", DummyFF)

    cap, _ = cf.open_capture(
        "rtsp://t",
        1,
        src_type="rtsp",
        backend_priority=["ffmpeg"],
        ready_frames=1,
        ready_timeout=1.0,
    )
    assert called["transport"] == "udp"
    data = json.loads(fake_r.get("camera_debug:1"))
    assert data["probe"]["transport"] == "udp"
    cap.release()
    cf.redis_client = None


def test_open_capture_returns_successful_transport(monkeypatch):
    class DummyFF(BaseCameraStream):
        def __init__(self, *a, **k):
            self.successful_transport = "udp"
            self.transport = k.get("transport")
            super().__init__(k.get("buffer_size", 3))

        def _init_stream(self):
            pass

        def _read_frame(self):
            return True, np.zeros((1, 1, 3), dtype=np.uint8)

        def read_latest(self):
            return True, np.zeros((1, 1, 3), dtype=np.uint8)

        def _release_stream(self):
            pass

    monkeypatch.setattr(cf, "FFmpegCameraStream", DummyFF)
    cap, transport = cf.open_capture(
        "rtsp://t",
        1,
        src_type="rtsp",
        backend_priority=["ffmpeg"],
        ready_frames=1,
        ready_timeout=1.0,
    )
    assert transport == "udp"
    cap.release()


def test_pipeline_arg_precedence(monkeypatch):
    monkeypatch.setattr(cf, "GstCameraStream", DummyGst)
    monkeypatch.setitem(shared_config, "enable_gstreamer", True)
    fake_r = fakeredis.FakeRedis(decode_responses=True)
    cf.redis_client = fake_r
    fake_r.hset("camera:1", mapping={"pipeline": "redis"})
    cap, _ = cf.open_capture(
        "rtsp://test",
        1,
        src_type="rtsp",
        backend_priority=["gstreamer"],
        pipeline="arg",
    )
    assert cap.pipeline == "arg"
    cap.release()
    cf.redis_client = None


def test_pipeline_redis_fallback(monkeypatch):
    monkeypatch.setattr(cf, "GstCameraStream", DummyGst)
    monkeypatch.setitem(shared_config, "enable_gstreamer", True)
    fake_r = fakeredis.FakeRedis(decode_responses=True)
    cf.redis_client = fake_r
    fake_r.hset("camera:1", mapping={"pipeline": "redis"})
    cap, _ = cf.open_capture(
        "rtsp://test",
        1,
        src_type="rtsp",
        backend_priority=["gstreamer"],
    )
    assert cap.pipeline == "redis"
    cap.release()
    cf.redis_client = None


def test_ready_timeout_allows_slow_start(monkeypatch):
    monkeypatch.setitem(shared_config, "enable_gstreamer", False)
    monkeypatch.setitem(shared_config, "ready_timeout", 0.1)

    class SlowFF(BaseCameraStream):
        def __init__(self, *args, **kwargs):
            self.start = time.time()
            super().__init__(kwargs.get("buffer_size", 3))

        def _init_stream(self):
            pass

        def _read_frame(self):
            if time.time() - self.start > 0.2:
                return True, np.zeros((1, 1, 3), dtype=np.uint8)
            return False, None

        def read_latest(self):
            return self._read_frame()

        def _release_stream(self):
            pass

    monkeypatch.setattr(cf, "FFmpegCameraStream", SlowFF)

    with pytest.raises(cf.StreamUnavailable):
        cf.open_capture(
            "rtsp://slow",
            1,
            src_type="rtsp",
            backend_priority=["ffmpeg"],
            ready_frames=1,
        )

    cap, _ = cf.open_capture(
        "rtsp://slow",
        1,
        src_type="rtsp",
        backend_priority=["ffmpeg"],
        ready_frames=1,
        ready_timeout=0.5,
    )
    assert isinstance(cap, SlowFF)
    cap.release()


def test_open_capture_waits_for_frames(monkeypatch):
    monkeypatch.setitem(shared_config, "enable_gstreamer", False)

    class SlowInit(BaseCameraStream):
        def __init__(self, *args, **kwargs):
            self.start = time.time()
            super().__init__(kwargs.get("buffer_size", 3))

        def _init_stream(self):
            pass

        def _read_frame(self):
            if time.time() - self.start < 0.2:
                return False, None
            return True, np.zeros((1, 1, 3), dtype=np.uint8)

        def _release_stream(self):
            pass

    monkeypatch.setattr(cf, "FFmpegCameraStream", SlowInit)

    t0 = time.time()
    cap, _ = cf.open_capture(
        "rtsp://delay",
        1,
        src_type="rtsp",
        backend_priority=["ffmpeg"],
        ready_frames=1,
        ready_timeout=1.0,
    )
    elapsed = time.time() - t0
    assert elapsed >= 0.2
    cap.release()


def test_default_priority_excludes_gstreamer_when_disabled(monkeypatch):
    monkeypatch.setitem(shared_config, "enable_gstreamer", False)

    def fail_gst(*a, **k):
        raise AssertionError("GStreamer should not be used")

    class DummyFFmpeg(BaseCameraStream):
        def __init__(self, *args, **kwargs):
            self.transport = kwargs.get("transport")
            super().__init__(kwargs.get("buffer_size", 3))

        def _init_stream(self):
            pass

        def _read_frame(self):
            return True, np.zeros((1, 1, 3), dtype=np.uint8)

        def _release_stream(self):
            pass

    monkeypatch.setattr(cf, "GstCameraStream", fail_gst)
    monkeypatch.setattr(cf, "FFmpegCameraStream", DummyFFmpeg)
    cap, _ = cf.open_capture(
        "rtsp://test",
        1,
        src_type="rtsp",
        backend_priority=None,
        ready_frames=1,
        for_display=True,
    )
    assert isinstance(cap, DummyFFmpeg)
    cap.release()


def test_fallback_with_gstreamer_enabled(monkeypatch):
    monkeypatch.setitem(shared_config, "enable_gstreamer", True)

    class ErrGst(BaseCameraStream):
        def __init__(self, *a, **k):
            raise RuntimeError("gst fail")

    class DummyFFmpeg(BaseCameraStream):
        def __init__(self, *args, **kwargs):
            self.transport = kwargs.get("transport")
            super().__init__(kwargs.get("buffer_size", 3))

        def _init_stream(self):
            pass

        def _read_frame(self):
            return True, np.zeros((1, 1, 3), dtype=np.uint8)

        def _release_stream(self):
            pass

    monkeypatch.setattr(cf, "GstCameraStream", ErrGst)
    monkeypatch.setattr(cf, "FFmpegCameraStream", DummyFFmpeg)
    cap, _ = cf.open_capture("rtsp://test", 1, src_type="rtsp", backend_priority=None)
    assert isinstance(cap, DummyFFmpeg)
    cap.release()


def test_fallback_to_opencv_when_ffmpeg_fails(monkeypatch):
    monkeypatch.setitem(shared_config, "enable_gstreamer", False)

    def fail_gst(*a, **k):
        raise AssertionError("GStreamer should not be used")

    class ErrFFmpeg(BaseCameraStream):
        def __init__(self, *a, **k):
            raise RuntimeError("ffmpeg fail")

    class DummyOpenCV(BaseCameraStream):
        def __init__(self, *args, **kwargs):
            super().__init__(kwargs.get("buffer_size", 3))

        def _init_stream(self):
            pass

        def _read_frame(self):
            return True, np.zeros((1, 1, 3), dtype=np.uint8)

        def _release_stream(self):
            pass

    monkeypatch.setattr(cf, "GstCameraStream", fail_gst)
    monkeypatch.setattr(cf, "FFmpegCameraStream", ErrFFmpeg)
    monkeypatch.setattr(cf, "OpenCVCameraStream", DummyOpenCV)
    cap, _ = cf.open_capture(
        "rtsp://test",
        1,
        src_type="rtsp",
        backend_priority=None,
        ready_frames=1,
        for_display=True,
    )
    assert isinstance(cap, DummyOpenCV)
    cap.release()


def test_open_capture_ffmpeg_defaults(monkeypatch):
    monkeypatch.setattr(
        cf, "get_sync_client", lambda: (_ for _ in ()).throw(RuntimeError("no redis"))
    )
    cf.redis_client = None
    monkeypatch.setattr(cf, "get_stream_resolution", lambda url: (2, 2))
    monkeypatch.setattr(
        ffmpeg,
        "probe",
        lambda url: {"streams": [{"codec_type": "video", "width": 2, "height": 2}]},
    )

    class DummyStdout:
        def read(self, n):
            return b"\x00" * n

    class DummyPopen:
        def __init__(self, *args, **kwargs):
            self.stdout = DummyStdout()
            self.stderr = io.BytesIO()

        def poll(self):
            return None

        def kill(self):
            pass

    monkeypatch.setattr(subprocess, "Popen", lambda *a, **k: DummyPopen())
    cap, _ = cf.open_capture(
        "rtsp://test", 1, src_type="rtsp", backend_priority=["ffmpeg"], ready_frames=1
    )
    from modules.ffmpeg_stream import FFmpegCameraStream

    assert isinstance(cap, FFmpegCameraStream)
    assert "-rtsp_transport" in cap.pipeline
    assert "-f" in cap.pipeline and "rawvideo" in cap.pipeline

    cap.release()
