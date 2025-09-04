"""Separate renderer process for drawing overlays.

The renderer receives tracking metadata via a ``multiprocessing.Queue`` and
reads frames from shared memory to avoid copying between processes.  The
resulting overlay frame is written back to shared memory for consumers.
"""

from __future__ import annotations

import multiprocessing as mp
from multiprocessing import shared_memory
from typing import Dict, Tuple

import numpy as np

from .overlay import draw_overlays


def _render_loop(
    shm_in_name: str,
    shm_out_name: str,
    queue: mp.Queue,
    shape: Tuple[int, int, int],
) -> None:
    """Process target that draws overlays on frames in shared memory."""
    shm_in = shared_memory.SharedMemory(name=shm_in_name)
    shm_out = shared_memory.SharedMemory(name=shm_out_name)
    frame = np.ndarray(shape, dtype=np.uint8, buffer=shm_in.buf)
    out = np.ndarray(shape, dtype=np.uint8, buffer=shm_out.buf)
    while True:
        msg = queue.get()
        if msg is None:
            break
        tracks: Dict[int, dict] = msg["tracks"]
        flags: Dict[str, bool] = msg["flags"]
        out[:] = frame
        draw_overlays(
            out,
            tracks,
            flags.get("show_ids", False),
            flags.get("show_track_lines", False),
            flags.get("show_lines", False),
            msg.get("line_orientation", "vertical"),
            msg.get("line_ratio", 0.5),
            flags.get("show_counts", False),
            msg.get("in_count", 0),
            msg.get("out_count", 0),
            msg.get("face_boxes"),
        )
    shm_in.close()
    shm_out.close()


class RendererProcess:
    """Manage the lifecycle of the renderer subprocess."""

    def __init__(self, shape: Tuple[int, int, int]) -> None:
        ctx = mp.get_context("spawn")
        nbytes = int(np.prod(shape) * np.dtype("uint8").itemsize)
        self.shm_in = shared_memory.SharedMemory(create=True, size=nbytes)
        self.shm_out = shared_memory.SharedMemory(create=True, size=nbytes)
        self.frame = np.ndarray(shape, dtype=np.uint8, buffer=self.shm_in.buf)
        self.output = np.ndarray(shape, dtype=np.uint8, buffer=self.shm_out.buf)
        self.queue: mp.Queue = ctx.Queue(maxsize=1)
        self.process = ctx.Process(
            target=_render_loop,
            args=(self.shm_in.name, self.shm_out.name, self.queue, shape),
            daemon=True,
        )
        self.process.start()

    def close(self) -> None:
        """Shut down the renderer process and release shared memory."""
        try:
            self.queue.put(None)
            if self.process.is_alive():
                self.process.join()
        finally:
            self.shm_in.close()
            self.shm_in.unlink()
            self.shm_out.close()
            self.shm_out.unlink()
