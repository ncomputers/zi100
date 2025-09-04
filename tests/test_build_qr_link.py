from starlette.requests import Request

from modules import gatepass_service
from config import config as cfg


def test_build_qr_link_uses_request_base(monkeypatch):
    monkeypatch.setitem(cfg, "base_url", "")
    scope = {
        "type": "http",
        "scheme": "http",
        "server": ("example.com", 80),
        "path": "/",
        "headers": [],
    }
    req = Request(scope)
    link = gatepass_service.build_qr_link("ABC123", req)
    assert link == "http://example.com/gatepass/view/ABC123"
