"""Camera stream wrapper using GStreamer pipelines."""

from __future__ import annotations

from typing import Optional, Tuple

import cv2
import numpy as np
from loguru import logger

try:  # optional heavy dependency
    import torch  # type: ignore
except ModuleNotFoundError:  # pragma: no cover - torch is optional in tests
    torch = None

logger = logger.bind(module="gstreamer_stream")
from config import config as shared_config

from .base_camera import BaseCameraStream

GST_AVAILABLE: Optional[bool] = None
GSTREAMER_STATUS_LOGGED = False
Gst = None


def _ensure_gst() -> bool:
    """Attempt to import GStreamer bindings if enabled in config."""
    global GST_AVAILABLE, Gst, GSTREAMER_STATUS_LOGGED
    if GST_AVAILABLE is not None:
        return GST_AVAILABLE

    if not shared_config.get("enable_gstreamer", False):
        if not GSTREAMER_STATUS_LOGGED:
            logger.info("GStreamer intentionally disabled via config")
            GSTREAMER_STATUS_LOGGED = True
        GST_AVAILABLE = False
        return False
    try:  # pragma: no cover - depends on system packages
        import gi

        gi.require_version("Gst", "1.0")
        from gi.repository import Gst as GstModule

        GstModule.init(None)
        Gst = GstModule
        if not GSTREAMER_STATUS_LOGGED:
            logger.info("GStreamer bindings loaded")
            GSTREAMER_STATUS_LOGGED = True
        GST_AVAILABLE = True
    except (ImportError, ValueError, RuntimeError) as e:
        Gst = None
        if not GSTREAMER_STATUS_LOGGED:
            logger.error(f"GStreamer bindings not available: {e}")
            GSTREAMER_STATUS_LOGGED = True
        GST_AVAILABLE = False
    return GST_AVAILABLE


def _build_pipeline(
    url: str,
    width: int | None,
    height: int | None,
    transport: str,
    extra_pipeline: str | None,
) -> str:
    base = (
        f'rtspsrc location="{url}" protocols={transport} latency=100 ! '
        "rtph264depay ! h264parse ! avdec_h264 ! videoconvert"
    )
    if extra_pipeline:
        base += f" ! {extra_pipeline}"
    base += " ! video/x-raw,format=BGR"
    if width and height:
        base += f",width={width},height={height}"
    return (
        base + " ! queue max-size-buffers=1 leaky=downstream ! "
        "appsink name=appsink drop=true sync=false max-buffers=1"
    )


class GstCameraStream(BaseCameraStream):
    """Capture video frames using a GStreamer pipeline."""

    # __init__ routine
    def __init__(
        self,
        url: str,
        width: Optional[int] = None,
        height: Optional[int] = None,
        rtsp_transport: str = "tcp",
        use_gpu: bool = True,
        buffer_size: int = 3,
        buffer_seconds: int | None = None,
        start_thread: bool = True,
        extra_pipeline: str | None = None,
        pipeline: str | None = None,
        cam_id: int | str | None = None,
    ) -> None:
        from utils.url import normalize_stream_url

        url = normalize_stream_url(url.strip())
        self.url = url
        self.width = width
        self.height = height
        self.rtsp_transport = rtsp_transport
        self.logger = logger.bind(cam_id=cam_id, backend="gstreamer")
        self.use_gpu = use_gpu and torch is not None and torch.cuda.is_available()
        if pipeline:
            self.pipeline = pipeline
        else:
            self.pipeline = _build_pipeline(
                self.url, width, height, self.rtsp_transport, extra_pipeline
            )
            if extra_pipeline:
                self.logger.info("GStreamer custom pipeline: {}", extra_pipeline)
        # store the pipeline string so it can be referenced even if initialization fails
        self.last_pipeline: str = self.pipeline
        self.pipe: Optional["Gst.Pipeline"] = None
        self.appsink: Optional["Gst.Element"] = None
        self.last_status: str = "ok"
        self.last_error: str = ""
        super().__init__(buffer_size, start_thread=start_thread)

    # Internal -----------------------------------------------------------------
    # _init_stream routine
    def _init_stream(self) -> None:
        if not _ensure_gst():
            return
        try:
            self.pipe = Gst.parse_launch(self.pipeline)
            self.appsink = self.pipe.get_by_name("appsink")
            self.pipe.set_state(Gst.State.PLAYING)
        except (RuntimeError, ValueError) as e:
            self.logger.error(
                "GStreamer pipeline failed to open: {} ({})",
                self.pipeline,
                e,
            )
            self.pipe = None
            self.appsink = None
            self.last_status = "error"
            self.last_error = str(e)
            self.last_pipeline = self.pipeline

    # _read_frame routine
    def _read_frame(self) -> Tuple[bool, Optional[np.ndarray]]:
        if not self.appsink:
            return False, None
        sample = self.appsink.emit("try-pull-sample", 0)
        if sample is None:
            return False, None
        buf = sample.get_buffer()
        caps = sample.get_caps()
        struct = caps.get_structure(0)
        width = struct.get_value("width")
        height = struct.get_value("height")
        success, map_info = buf.map(Gst.MapFlags.READ)
        if not success:
            return False, None
        try:
            frame = (
                np.frombuffer(map_info.data, dtype=np.uint8)
                .reshape((height, width, 3))
                .copy()
            )
        except ValueError:
            frame = None
        buf.unmap(map_info)
        return (frame is not None), frame

    # _release_stream routine
    def _release_stream(self) -> None:
        if self.pipe:
            self.pipe.set_state(Gst.State.NULL)
            self.pipe = None
            self.appsink = None
