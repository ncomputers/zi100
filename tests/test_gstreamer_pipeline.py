"""Tests for GStreamer camera pipeline assembly."""

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


class DummyCuda:
    @staticmethod
    def getCudaEnabledDeviceCount():
        return 0


sys.modules.setdefault("cv2", type("cv2", (), {"cuda": DummyCuda()}))


class DummyLogger:
    def bind(self, **kwargs):
        return self

    def info(self, *args, **kwargs):
        pass

    def error(self, *args, **kwargs):
        pass


sys.modules.setdefault("loguru", type("loguru", (), {"logger": DummyLogger()}))

from modules import gstreamer_stream as gst_mod
from modules.gstreamer_stream import GstCameraStream


def test_build_pipeline_helper():
    extra = "clockoverlay"
    pipeline = gst_mod._build_pipeline("rtsp://demo", 640, 480, "tcp", extra)
    expected = (
        'rtspsrc location="rtsp://demo" protocols=tcp latency=100 ! '
        "rtph264depay ! h264parse ! avdec_h264 ! videoconvert ! "
        f"{extra} ! video/x-raw,format=BGR,width=640,height=480 ! "
        "queue max-size-buffers=1 leaky=downstream ! "
        "appsink name=appsink drop=true sync=false max-buffers=1"
    )
    assert pipeline == expected


def test_custom_pipeline_inserted_once():
    extra = "clockoverlay"
    stream = GstCameraStream(
        "rtsp://demo", width=640, height=480, extra_pipeline=extra, start_thread=False
    )
    assert stream.pipeline.count(extra) == 1
    expected = (
        f'rtspsrc location="{stream.url}" protocols=tcp latency=100 ! '
        "rtph264depay ! h264parse ! avdec_h264 ! videoconvert ! "
        f"{extra} ! video/x-raw,format=BGR,width=640,height=480 ! "
        "queue max-size-buffers=1 leaky=downstream ! "
        "appsink name=appsink drop=true sync=false max-buffers=1"
    )
    assert stream.pipeline == expected


def test_pipeline_retained_on_init_failure(monkeypatch):
    """Even when initialization fails, the attempted pipeline is retained."""
    monkeypatch.setattr(gst_mod, "_ensure_gst", lambda: True)

    class DummyGst:
        class State:
            PLAYING = 0

        @staticmethod
        def parse_launch(pipeline):
            raise RuntimeError("bad pipeline")

    monkeypatch.setattr(gst_mod, "Gst", DummyGst)
    stream = GstCameraStream("rtsp://demo", start_thread=False)
    stream._init_stream()
    assert stream.last_status == "error"
    assert stream.last_pipeline == stream.pipeline
