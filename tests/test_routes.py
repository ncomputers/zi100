"""Purpose: Test routes module."""

import asyncio
import sys
from pathlib import Path

import fakeredis

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from routers import entry, ppe_reports, reports, visitor


# DummyRequest class encapsulates dummyrequest behavior
class DummyRequest:
    # __init__ routine
    def __init__(self):
        self.session = {"user": {"role": "admin"}}


class AnonRequest:
    """Request with no authenticated user."""

    def __init__(self):
        self.session = {}


# Test vms paths
def test_vms_paths(tmp_path):
    cfg = {"features": {"visitor_mgmt": True}, "track_objects": []}
    r = fakeredis.FakeRedis()
    (tmp_path / "vms.html").write_text("{{request}}")
    (tmp_path / "invite_panel.html").write_text("{{request}}")
    (tmp_path / "visitor_report.html").write_text("{{request}}")
    (tmp_path / "report.html").write_text("{{request}}")
    (tmp_path / "ppe_report.html").write_text("{{request}}")
    entry.init_context(cfg, r, str(tmp_path))
    visitor.init_context(cfg, r, str(tmp_path), [])
    reports.init_context(cfg, {}, r, str(tmp_path), [])
    ppe_reports.init_context(cfg, {}, r, str(tmp_path))

    req = DummyRequest()
    resp1 = asyncio.run(entry.vms_page(req))
    assert resp1.status_code == 200 and resp1.template.name == "vms.html"
    resp2 = asyncio.run(visitor.invite_panel(req))
    assert resp2.status_code == 200 and resp2.template.name == "invite_panel.html"
    resp3 = asyncio.run(visitor.visitor_report(req))
    assert resp3.status_code == 200 and resp3.template.name == "visitor_report.html"
    resp4 = asyncio.run(reports.report_page(req))
    assert resp4.status_code == 200 and resp4.template.name == "report.html"
    resp5 = asyncio.run(ppe_reports.ppe_report_page(req))
    assert resp5.status_code == 200 and resp5.template.name == "ppe_report.html"
    # restore templates path for subsequent tests
    entry.init_context(cfg, r, str(ROOT / "templates"))


def test_visitor_report_public(tmp_path):
    cfg = {"features": {"visitor_mgmt": True}, "track_objects": []}
    r = fakeredis.FakeRedis()
    (tmp_path / "visitor_report.html").write_text("{{request}}")
    visitor.init_context(cfg, r, str(tmp_path), [])
    req = AnonRequest()
    resp = asyncio.run(visitor.visitor_report(req))
    assert resp.status_code == 200 and resp.template.name == "visitor_report.html"
    assert resp.context.get("logged_in") is False


def test_vms_page_handles_redis_error(tmp_path):
    cfg = {"features": {"visitor_mgmt": True}, "track_objects": []}
    r = fakeredis.FakeRedis()
    (tmp_path / "vms.html").write_text("ok")
    entry.init_context(cfg, r, str(tmp_path))

    class FailRedis:
        def zrevrange(self, *a, **k):
            raise RuntimeError("down")

    entry.redis = FailRedis()
    req = DummyRequest()
    resp = asyncio.run(entry.vms_page(req))
    assert resp.status_code == 200
    # restore templates path for subsequent tests
    entry.init_context(cfg, r, str(ROOT / "templates"))
