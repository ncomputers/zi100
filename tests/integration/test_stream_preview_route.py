import numpy as np
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.routing import Mount

from routers import blueprints, dashboard


class DummyTracker:
    def __init__(self):
        frame = np.zeros((2, 2, 3), dtype=np.uint8)
        self.output_frame = frame
        self.raw_frame = frame
        self.fps = 1
        self.viewers = 0
        self.restart_capture = False


def _app(monkeypatch) -> FastAPI:
    app = FastAPI()
    monkeypatch.setattr(blueprints, "MODULES", [dashboard])
    app.state.trackers = {}
    blueprints.register_blueprints(app)
    return app


def test_dashboard_router_registered(monkeypatch) -> None:
    app = _app(monkeypatch)
    paths = {getattr(r, "path", None) for r in app.routes}
    assert "/stream/preview/{cam_id}" in paths


def test_stream_route_not_masked(monkeypatch) -> None:
    app = _app(monkeypatch)
    assert not any(isinstance(r, Mount) and r.path == "/stream" for r in app.routes)


def test_stream_preview_endpoint(monkeypatch) -> None:
    app = _app(monkeypatch)
    monkeypatch.setattr("routers.dashboard.require_roles", lambda *a, **k: {})
    tracker = DummyTracker()
    app.state.trackers[1] = tracker
    client = TestClient(app)
    resp = client.head("/stream/preview/1")
    assert resp.status_code == 405
