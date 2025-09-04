import asyncio
import json
import smtplib

import pytest
from starlette.requests import Request


@pytest.fixture(autouse=True, scope="session")
def _patch_health_loop():
    import routers.cameras as cam

    if not hasattr(cam, "_health_loop"):
        cam._health_loop = lambda: None


def test_send_email_auth_error(monkeypatch):
    from modules import email_utils

    class DummySMTP:
        def __init__(self, *args, **kwargs):
            pass

        def ehlo(self):
            pass

        def starttls(self):
            pass

        def login(self, user, password):
            raise smtplib.SMTPAuthenticationError(535, b"auth failed")

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            pass

    monkeypatch.setattr(email_utils.smtplib, "SMTP", DummySMTP)
    cfg = {"smtp_host": "localhost", "smtp_port": 587, "smtp_user": "u"}
    success, err, _, _ = email_utils.send_email("s", "b", ["r"], cfg=cfg)
    assert not success
    assert "auth failed" in err


def test_send_email_connection_error(monkeypatch):
    from modules import email_utils

    class FailSMTP:
        def __init__(self, *args, **kwargs):
            raise ConnectionRefusedError

    monkeypatch.setattr(email_utils.smtplib, "SMTP", FailSMTP)
    cfg = {"smtp_host": "localhost", "smtp_port": 587}
    result = email_utils.send_email("s", "b", ["r"], cfg=cfg)
    assert result[0] is False
    assert result[1] == "ConnectionRefusedError"


def test_email_test_missing_host(monkeypatch):
    from routers import settings

    monkeypatch.setattr(settings, "cfg", {}, raising=False)
    monkeypatch.setitem(settings.cfg.setdefault("email", {}), "smtp_host", "")

    async def receive():
        return {
            "type": "http.request",
            "body": json.dumps({"recipient": "a@example.com"}).encode(),
            "more_body": False,
        }

    req = Request({"type": "http"}, receive)
    result = asyncio.run(settings.settings_email_test(req))
    assert result["error"] == "missing_smtp_host"
    assert not result["sent"]

