from modules import email_utils


def test_build_message_html_and_plain():
    cfg = {"from_addr": "from@example.com"}
    msg_plain = email_utils._build_message("Sub", "Body", ["to@example.com"], cfg)
    assert msg_plain.get_content_subtype() == "plain"
    msg_html = email_utils._build_message(
        "Sub", "<p>Body</p>", ["to@example.com"], cfg, html=True
    )
    assert msg_html.get_content_subtype() == "html"
    assert msg_html["To"] == "to@example.com"


def test_build_message_with_attachment():
    cfg = {"from_addr": "from@example.com"}
    msg = email_utils._build_message(
        "Sub",
        "Body",
        ["to@example.com"],
        cfg,
        attachment=b"hi",
        attachment_name="hi.txt",
        attachment_type="text/plain",
    )
    attachments = list(msg.iter_attachments())
    assert len(attachments) == 1
    part = attachments[0]
    assert part.get_filename() == "hi.txt"
    assert part.get_content_type() == "text/plain"
    assert part.get_content() == "hi"


def test_auth_smtp_username_password():
    calls = {}

    class FakeSMTP:
        def docmd(self, *args, **kwargs):
            raise AssertionError("docmd should not be called")

        def login(self, user, pwd):
            calls["user"] = user
            calls["pwd"] = pwd

    err = email_utils._auth_smtp(FakeSMTP(), {"smtp_user": "u", "smtp_pass": "p"})
    assert err is None
    assert calls["user"] == "u"
    assert calls["pwd"] == "p"


def test_send_email_uses_ssl_when_configured(monkeypatch):

    calls: dict[str, bool] = {}

    class DummyServer:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            pass

        def ehlo(self):
            pass

        def starttls(self):
            calls["starttls"] = True

        def login(self, *a, **k):
            pass

        def mail(self, *a, **k):
            return 250, b"ok"

        def rcpt(self, *a, **k):
            return 250, b"ok"

        def data(self, *a, **k):
            return 250, b"ok"

    class DummySSL(DummyServer):
        def __init__(self, *a, **k):
            calls["ssl"] = True

    class DummySMTP(DummyServer):
        def __init__(self, *a, **k):
            calls["smtp"] = True

    monkeypatch.setattr(email_utils.smtplib, "SMTP_SSL", DummySSL)
    monkeypatch.setattr(email_utils.smtplib, "SMTP", DummySMTP)
    monkeypatch.setattr(email_utils, "_auth_smtp", lambda *a, **k: None)

    class DummyMsg(dict):
        def as_string(self):
            return "msg"

    monkeypatch.setattr(
        email_utils,
        "_build_message",
        lambda *a, **k: DummyMsg({"From": "f", "Message-ID": "id"}),
    )

    success, _, _, _ = email_utils.send_email(
        "Sub",
        "Body",
        ["to@example.com"],
        cfg={"smtp_host": "h", "smtp_port": 465, "use_tls": False},
    )

    assert success
    assert calls.get("ssl") and not calls.get("smtp")
    assert "starttls" not in calls


def test_send_email_starttls_on_port_465(monkeypatch):
    calls: dict[str, bool] = {}

    class DummySMTP:
        def __init__(self, *a, **k):
            calls["smtp"] = True

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            pass

        def ehlo(self):
            pass

        def starttls(self):
            calls["starttls"] = True

        def login(self, *a, **k):
            pass

        def mail(self, *a, **k):
            return 250, b"ok"

        def rcpt(self, *a, **k):
            return 250, b"ok"

        def data(self, *a, **k):
            return 250, b"ok"

    monkeypatch.setattr(email_utils.smtplib, "SMTP", DummySMTP)
    monkeypatch.setattr(email_utils, "_auth_smtp", lambda *a, **k: None)

    class DummyMsg(dict):
        def as_string(self):
            return "msg"

    monkeypatch.setattr(
        email_utils,
        "_build_message",
        lambda *a, **k: DummyMsg({"From": "f", "Message-ID": "id"}),
    )

    success, _, _, _ = email_utils.send_email(
        "Sub",
        "Body",
        ["to@example.com"],
        cfg={"smtp_host": "h", "smtp_port": 465, "use_tls": True},
    )

    assert success
    assert calls.get("smtp")
    assert calls.get("starttls")
