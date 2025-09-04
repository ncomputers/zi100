"""Simple OpenCV VideoCapture wrapper with a rolling buffer.

`buffer_size` tunes the underlying ``cv2.CAP_PROP_BUFFERSIZE`` to trade
latency for resilience. Smaller values reduce lag for local cameras.
"""

from __future__ import annotations

import platform
from typing import Optional, Tuple

import cv2
import numpy as np
from loguru import logger

from .base_camera import BaseCameraStream

logger = logger.bind(module="opencv_stream")


# OpenCVCameraStream class encapsulates opencvcamerastream behavior
class OpenCVCameraStream(BaseCameraStream):
    # __init__ routine
    def __init__(
        self,
        src,
        width: Optional[int] = None,
        height: Optional[int] = None,
        buffer_size: int = 3,
        cam_id: int | str | None = None,
    ) -> None:
        from utils.url import normalize_stream_url

        self.src = normalize_stream_url(src) if isinstance(src, str) else src
        self.pipeline = str(self.src)
        self.width = width
        self.height = height
        self.logger = logger.bind(cam_id=cam_id, backend="opencv")
        self.cap: Optional[cv2.VideoCapture] = None
        self.last_status: str = "ok"
        self.last_error: str = ""
        super().__init__(buffer_size)

    # _init_stream routine
    def _init_stream(self) -> None:
        src = self.src
        if isinstance(src, str) and src.isdigit():
            src = int(src)
        if platform.system() == "Windows":
            self.cap = cv2.VideoCapture(src, cv2.CAP_DSHOW)
        else:
            self.cap = cv2.VideoCapture(src)
        if self.width and self.height:
            self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
            self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
        if hasattr(cv2, "CAP_PROP_BUFFERSIZE"):
            self.cap.set(cv2.CAP_PROP_BUFFERSIZE, self.buffer_size)
        if not self.cap.isOpened():
            self.last_status = "error"
            self.last_error = "could not open device"
            self.logger.error("OpenCV VideoCapture failed to open: {}", self.src)

    # _read_frame routine
    def _read_frame(self) -> Tuple[bool, Optional[np.ndarray]]:
        if not self.cap:
            self.last_status = "error"
            self.last_error = "capture not initialized"
            return False, None
        ret, frame = self.cap.read()
        if not ret or frame is None:
            self.last_status = "error"
            self.last_error = "failed to read frame"
            return False, None
        self.last_status = "ok"
        self.last_error = ""
        return True, frame

    # _release_stream routine
    def _release_stream(self) -> None:
        if self.cap:
            self.cap.release()
            self.cap = None
