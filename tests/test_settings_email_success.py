import pytest


@pytest.fixture(autouse=True, scope="session")
def _patch_health_loop():
    import routers.cameras as cam

    if not hasattr(cam, "_health_loop"):
        cam._health_loop = lambda: None


def test_email_test_uses_payload_config(client, monkeypatch):
    from routers import settings

    monkeypatch.setitem(settings.cfg, "email", {})

    captured = {}

    def fake_send_email(*args, **kwargs):
        captured.update(kwargs.get("cfg", {}))
        return True, "", None, None

    monkeypatch.setattr("routers.settings.send_email", fake_send_email)

    payload = {
        "recipient": "to@example.com",
        "smtp_host": "smtp.example.com",
        "smtp_port": 25,
        "smtp_user": "user",
        "smtp_pass": "pass",
        "use_tls": True,
        "use_ssl": False,
        "from_addr": "from@example.com",
    }

    r = client.post("/settings/email/test", json=payload)
    assert r.status_code == 200
    assert r.json() == {"sent": True}
    assert captured["smtp_host"] == "smtp.example.com"
    assert captured["smtp_port"] == 25
    assert captured["from_addr"] == "from@example.com"
