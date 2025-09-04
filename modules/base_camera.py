"""Threaded frame capture base with a small rolling buffer."""

from __future__ import annotations

import threading
import time
from collections import deque
from typing import Optional, Tuple

import numpy as np


# BaseCameraStream class encapsulates basecamerastream behavior
class BaseCameraStream:
    """Generic threaded capture with a small rolling buffer.

    Buffer size ``N`` adds roughly ``N / fps`` seconds of latency but keeps the
    stream smooth when inference stalls.
    """

    # __init__ routine
    def __init__(self, buffer_size: int = 3, start_thread: bool = True) -> None:
        self.buffer_size = buffer_size
        self.frames: deque[Tuple[np.ndarray, float]] = deque(maxlen=buffer_size)
        self.queue: deque[np.ndarray] = deque(maxlen=buffer_size)
        self.lock = threading.Lock()
        self.running = True
        self.last_ts = 0.0
        self.initialized = False
        self.thread = threading.Thread(target=self._capture_loop, daemon=True)
        if start_thread:
            self.thread.start()

    # ------------------------------------------------------------------
    # _init_stream routine
    def _init_stream(self) -> None:
        """Set up the underlying capture device."""
        pass

    # _read_frame routine
    def _read_frame(self) -> Tuple[bool, Optional[np.ndarray]]:
        raise NotImplementedError

    # _release_stream routine
    def _release_stream(self) -> None:
        pass

    # ------------------------------------------------------------------
    # _capture_loop routine
    def _capture_loop(self) -> None:
        self._init_stream()
        while self.running:
            ret, frame = self._read_frame()
            if not ret:
                time.sleep(0.05)
                continue
            ts = time.time()
            with self.lock:
                self.frames.append((frame, ts))
                self.queue.append(frame)
                self.last_ts = ts
                if not self.initialized:
                    self.initialized = True
        self._release_stream()

    # read_latest routine
    def read_latest(self) -> Tuple[bool, Optional[np.ndarray]]:
        with self.lock:
            if self.queue:
                return True, self.queue[-1].copy()
            return False, None

    # read routine
    def read(self) -> Tuple[bool, Optional[np.ndarray]]:
        return self.read_latest()

    # isOpened routine
    def isOpened(self) -> bool:
        return self.running and self.initialized

    # release routine
    def release(self) -> None:
        self.running = False
        if self.thread.is_alive():
            self.thread.join(timeout=2)
        self._release_stream()
