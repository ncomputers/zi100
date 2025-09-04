"""Ensure cameras are hidden by default on dashboard."""

import asyncio
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.modules.setdefault("cv2", types.SimpleNamespace())

from routers import dashboard  # noqa: E402


class DummyRequest:
    def __init__(self):
        self.session = {"user": {"role": "admin"}}
        self.query_params = {}


class DummyTemplates:
    def TemplateResponse(self, name, context):  # pragma: no cover - simple stub
        return types.SimpleNamespace(context=context)


class DummyRedis:
    def mget(self, keys):
        return [0] * len(keys)


def _run_index(cams):
    cfg = {"track_objects": ["person"], "max_capacity": 10, "warn_threshold": 80}
    templates = DummyTemplates()
    req = DummyRequest()
    redis = DummyRedis()
    return asyncio.run(
        dashboard.index(
            req, cfg=cfg, trackers_map={}, cams=cams, redis=redis, templates=templates
        )
    )


def test_new_camera_hidden_until_enabled():
    cams = [{"id": 1, "name": "Cam 1"}]
    resp = _run_index(cams)
    assert resp.context["cameras"] == []

    cams[0]["show"] = True
    resp = _run_index(cams)
    assert resp.context["cameras"][0]["id"] == 1
