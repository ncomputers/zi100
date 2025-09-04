from starlette.requests import Request

import routers.visitor as visitor
from routers.visitor.invites import _build_invite_link, _validate_invite_form


def _make_request(headers=None, scheme="http", server=("testserver", 80)):
    hdrs = []
    if headers:
        hdrs = [(k.lower().encode(), v.encode()) for k, v in headers.items()]
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/",
        "headers": hdrs,
        "scheme": scheme,
        "server": server,
    }
    return Request(scope)


def test_build_invite_link_uses_forwarded_proto():
    visitor.config_obj = {}
    req = _make_request(headers={"x-forwarded-proto": "https"})
    link = _build_invite_link(req, "ID123")
    assert link == "https://testserver/invite/form?id=ID123"


def test_build_invite_link_uses_config_base_url():
    visitor.config_obj = {"base_url": "https://example.com/app/"}
    req = _make_request()
    link = _build_invite_link(req, "ABC")
    assert link == "https://example.com/app/invite/form?id=ABC"


def test_validate_invite_form_missing_fields():
    form = {
        "name": " ",
        "phone": "",
        "visitor_type": "",
        "company": "ACME",
        "host": "",
        "visit_time": "",
        "purpose": "",
        "photo": "",
        "no_photo": "off",
    }
    errors = _validate_invite_form(form)
    assert {
        "name",
        "phone",
        "visitor_type",
        "host",
        "visit_time",
        "purpose",
        "photo",
    } <= errors.keys()


def test_validate_invite_form_photo_waived():
    form = {
        "name": "Bob",
        "phone": "123",
        "visitor_type": "Official",
        "company": "ACME",
        "host": "H",
        "visit_time": "2024-01-01 10:00",
        "purpose": "Meet",
        "photo": "",
        "no_photo": "on",
    }
    errors = _validate_invite_form(form)
    assert errors == {}
