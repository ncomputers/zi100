import asyncio
import types
import sys

import numpy as np
from starlette.requests import Request

sys.modules['cv2'] = types.SimpleNamespace()
from routers.dashboard import stream_preview


class DummyTracker:
    def __init__(self):
        frame = np.zeros((2, 2, 3), dtype=np.uint8)
        self.output_frame = frame
        self.raw_frame = frame
        self.fps = 1
        self.viewers = 0
        self.restart_capture = False


def test_stream_preview_returns_frame(monkeypatch):
    tracker = DummyTracker()
    monkeypatch.setattr("routers.dashboard.require_roles", lambda request, roles: {})

    async def _run() -> None:
        req = Request({"type": "http", "session": {"user": {"role": "viewer"}}})
        resp = await stream_preview(1, req, {1: tracker})
        gen = resp.response
        chunk = next(gen)
        assert b"--herebedragons" in chunk
        gen.close()

    asyncio.run(_run())
