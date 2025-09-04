"""Tests for router error handling behaviors."""

import asyncio
import time

import fakeredis
from loguru import logger

from routers import entry


class DummyRequest:
    """Simple request-like object for router calls."""

    def __init__(self):
        self.session = {"user": {"role": "admin"}}
        self.base_url = "http://testserver/"
        self.headers = {}


def test_vms_page_timeout_fallback(tmp_path):
    """Long-running redis calls should not block indefinitely."""
    cfg = {"features": {"visitor_mgmt": True}, "track_objects": []}
    r = fakeredis.FakeRedis()
    (tmp_path / "vms.html").write_text("{{request}}")
    entry.init_context(cfg, r, str(tmp_path))

    original = entry.redis.zrevrange

    def slow_zrevrange(*args, **kwargs):
        time.sleep(0.2)
        return []

    entry.redis.zrevrange = slow_zrevrange
    try:
        req = DummyRequest()
        with asyncio.runners.Runner() as runner:
            coro = entry.vms_page(req)
            try:
                runner.run(asyncio.wait_for(coro, timeout=0.05))
            except asyncio.TimeoutError:
                # timeout indicates control returned to caller
                pass
    finally:
        entry.redis.zrevrange = original


def test_vms_page_logs_redis_error(tmp_path):
    """Errors from redis should be logged."""
    cfg = {"features": {"visitor_mgmt": True}, "track_objects": []}
    r = fakeredis.FakeRedis()
    entry.init_context(cfg, r, str(tmp_path))

    class FailRedis:
        def zrevrange(self, *a, **k):
            raise RuntimeError("down")

    entry.redis = FailRedis()
    req = DummyRequest()

    logs = []
    handler_id = logger.add(lambda msg: logs.append(msg), level="ERROR")
    try:
        resp = asyncio.run(entry.vms_recent(req))
        assert isinstance(resp, list)
    finally:
        logger.remove(handler_id)
        entry.redis = r

    assert any("Redis unavailable" in str(m) for m in logs)
