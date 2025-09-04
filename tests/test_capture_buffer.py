"""Purpose: Test capture buffer module."""

import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from modules.base_camera import BaseCameraStream


# DummyStream class encapsulates dummystream behavior
class DummyStream(BaseCameraStream):
    # __init__ routine
    def __init__(self, fps=30, buffer_size=3):
        self.fps = fps
        super().__init__(buffer_size)

    # _init_stream routine
    def _init_stream(self):
        pass

    # _read_frame routine
    def _read_frame(self):
        time.sleep(1 / self.fps)
        return True, np.zeros((1, 1, 3), dtype=np.uint8)

    # _release_stream routine
    def _release_stream(self):
        pass


# Test capture buffer latency
def test_capture_buffer_latency():
    stream = DummyStream(fps=30, buffer_size=3)
    time.sleep(0.2)
    lags = []
    for _ in range(5):
        time.sleep(0.2)
        ret, frame = stream.read_latest()
        assert ret
        lag = time.time() - stream.last_ts
        lags.append(lag)
    stream.release()
    assert max(lags) <= 3 / 30 + 0.1
