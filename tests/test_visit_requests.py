import json
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from loguru import logger
from starlette.requests import Request

import routers.visitor as visitor
from routers.visitor import visit_requests


def test_require_visitor_mgmt_disabled(monkeypatch):
    monkeypatch.setitem(visit_requests.config_obj, "features", {"visitor_mgmt": False})
    with pytest.raises(HTTPException) as exc:
        visit_requests.require_visitor_mgmt()
    assert exc.value.status_code == 403


def test_require_visitor_mgmt_enabled(monkeypatch):
    monkeypatch.setitem(visit_requests.config_obj, "features", {"visitor_mgmt": True})
    assert isinstance(visit_requests.require_visitor_mgmt(), SimpleNamespace)


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.mark.anyio
async def test_visit_requests_page_redis_unavailable(monkeypatch):
    monkeypatch.setattr(visit_requests, "redis", None)
    scope = {
        "type": "http",
        "scheme": "http",
        "server": ("testserver", 80),
        "path": "/",
        "headers": [],
    }
    req = Request(scope)
    logs: list[str] = []
    handler_id = logger.add(lambda m: logs.append(m))
    with pytest.raises(HTTPException) as exc:
        await visit_requests.visit_requests_page(req, user=None)
    logger.remove(handler_id)
    assert exc.value.status_code == 503
    assert exc.value.detail == "redis_unavailable"
    assert any("redis connection missing" in m for m in logs)


@pytest.mark.anyio
async def test_visit_requests_page_success(monkeypatch):
    class DummyRedis:
        def zrevrange(self, key, start, end):
            return [json.dumps({"id": "1", "status": "pending", "ts": 0})]

    class DummyTemplates:
        def TemplateResponse(self, name, context):
            return SimpleNamespace(template=name, context=context)

    monkeypatch.setitem(visit_requests.config_obj, "features", {"visitor_mgmt": True})
    monkeypatch.setattr(visit_requests, "redis", DummyRedis())
    monkeypatch.setattr(visit_requests, "templates", DummyTemplates())

    scope = {
        "type": "http",
        "scheme": "http",
        "server": ("testserver", 80),
        "path": "/",
        "headers": [],
    }
    req = Request(scope)

    resp = await visit_requests.visit_requests_page(req, user={})
    assert resp.template == "visit_requests.html"
    assert resp.context["rows"][0]["status"] == "pending"


@pytest.mark.anyio
async def test_visit_requests_page_after_context_reload(monkeypatch, tmp_path):
    class DummyRedis:
        def __init__(self, entries):
            self.entries = entries

        def zrevrange(self, key, start, end):
            return self.entries

    class DummyTemplates:
        def TemplateResponse(self, name, context):
            return SimpleNamespace(template=name, context=context)

    monkeypatch.setattr(visitor, "Jinja2Templates", lambda directory: DummyTemplates())
    from modules import face_db, visitor_db

    monkeypatch.setattr(visitor_db, "init_db", lambda r: None)
    monkeypatch.setattr(face_db, "init", lambda c, r: None)

    cfg = {"features": {"visitor_mgmt": True}}
    r1 = DummyRedis([])
    visitor.init_context(cfg, r1, str(tmp_path))
    assert visit_requests.redis is r1

    entry = json.dumps({"id": "2", "status": "pending", "ts": 0})
    r2 = DummyRedis([entry])
    visitor.init_context(cfg, r2, str(tmp_path))
    assert visit_requests.redis is r2


    scope = {
        "type": "http",
        "scheme": "http",
        "server": ("testserver", 80),
        "path": "/",
        "headers": [],
    }
    req = Request(scope)
    resp = await visit_requests.visit_requests_page(req, user={})
    assert resp.template == "visit_requests.html"
    assert resp.context["rows"][0]["id"] == "2"

