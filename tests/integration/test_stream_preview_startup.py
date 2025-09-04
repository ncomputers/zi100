import asyncio

import numpy as np
from starlette.requests import Request

import routers.cameras as cameras
from routers.dashboard import stream_preview


class DummyTracker:
    def __init__(self):
        frame = np.zeros((2, 2, 3), dtype=np.uint8)
        self.output_frame = frame
        self.raw_frame = frame
        self.fps = 1
        self.viewers = 0
        self.restart_capture = False


def test_stream_preview_starts_tracker(monkeypatch):
    trackers = {}

    class DummyManager:
        def __init__(self):
            self.started = False
            self.cams = [{"id": 1}]

        def _find_cam(self, cid):
            for c in self.cams:
                if c["id"] == cid:
                    return c
            return None

        async def start(self, cid):
            self.started = True
            await asyncio.sleep(0.01)
            trackers[cid] = DummyTracker()

    mgr = DummyManager()
    monkeypatch.setattr(cameras, "camera_manager", mgr)
    monkeypatch.setattr("routers.dashboard.require_roles", lambda *a, **k: {})

    req = Request({"type": "http"})

    async def _run():
        resp = await stream_preview(1, req, trackers)
        gen = resp.response
        chunk = next(gen)
        assert b"--herebedragons" in chunk
        gen.close()

    asyncio.run(_run())
    assert mgr.started
