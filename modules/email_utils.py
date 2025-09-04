"""Utility functions for sending emails and handling templates."""

import logging
import smtplib
from email.message import EmailMessage
from email.utils import make_msgid
from typing import Any, Optional, Sequence


# build message and auth helpers
def _build_message(
    subject: str,
    body: str,
    recipients: Sequence[str],
    cfg: dict,
    *,
    html: bool = False,
    image: Optional[bytes] = None,
    attachment: Optional[bytes] = None,
    attachment_name: Optional[str] = None,
    attachment_type: Optional[str] = None,
) -> EmailMessage:
    """Assemble an email message with optional HTML body, images and attachments."""

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = cfg.get("from_addr", "")
    msg["To"] = ", ".join([r for r in recipients if r])
    msg_id = make_msgid()
    msg["Message-ID"] = msg_id
    if html:
        msg.set_content(body, subtype="html")
    else:
        msg.set_content(body)
    if image:
        msg.add_attachment(
            image,
            maintype="image",
            subtype="jpeg",
            filename="alert.jpg",
            cid=make_msgid()[1:-1],
            disposition="inline",
        )
    if attachment:
        maintype, subtype = (
            attachment_type.split("/")
            if attachment_type
            else ("application", "octet-stream")
        )
        msg.add_attachment(
            attachment,
            maintype=maintype,
            subtype=subtype,
            filename=attachment_name or "attachment",
        )
    return msg


def _auth_smtp(server: smtplib.SMTP, cfg: dict) -> Optional[str]:
    """Authenticate the SMTP ``server`` using username/password."""

    if cfg.get("smtp_user"):
        try:
            server.login(cfg.get("smtp_user"), cfg.get("smtp_pass", ""))
        except Exception as exc:  # pragma: no cover - login failure
            return str(exc)
    return None


# send_email routine
def send_email(
    subject: str,
    body: str,
    recipients: Sequence[str],
    cfg: dict,
    *,
    html: bool = False,
    image: Optional[bytes] = None,
    attachment: Optional[bytes] = None,
    attachment_name: Optional[str] = None,
    attachment_type: Optional[str] = None,
) -> tuple[bool, Optional[str], Optional[dict[str, Any]], Optional[str]]:
    """Send an email or log to console if SMTP is not configured.

    Parameters
    ----------
    subject: str
        Subject line for the email.
    body: str
        Email body. If ``html`` is True the body is treated as HTML.
    recipients: Sequence[str]
        List of recipient email addresses.
    cfg: dict
        SMTP configuration dictionary. Supports ``use_tls`` for STARTTLS and
        ``use_ssl`` for implicit TLS connections.
    html: bool, optional
        When True the message body is sent as HTML. Defaults to False.
    image: bytes, optional
        Optional JPEG image attachment added as ``alert.jpg``.
    attachment: bytes, optional
        Raw attachment content. When provided the data is attached to the message.
    attachment_name: str, optional
        Filename for the attachment.
    attachment_type: str, optional
        MIME type for the attachment. Defaults to ``application/octet-stream``.

    Returns
    -------
    tuple[bool, Optional[str], Optional[dict], Optional[str]]
        ``(True, None, responses, message_id)`` on success where ``responses``
        contains SMTP command codes and messages. On failure returns
        ``(False, error, responses, message_id)`` with any collected SMTP
        responses and optional message id.
    """
    host = cfg.get("smtp_host")
    if not host:
        err = "missing_smtp_host"
        logging.error("SMTP host not configured; email not sent")
        return False, err

    msg = _build_message(
        subject,
        body,
        recipients,
        cfg,
        html=html,
        image=image,
        attachment=attachment,
        attachment_name=attachment_name,
        attachment_type=attachment_type,
    )
    msg_id = msg["Message-ID"]
    responses: dict[str, Any] | None = None
    try:
        port = cfg.get("smtp_port", 587)
        use_tls = cfg.get("use_tls", True)
        use_ssl = cfg.get("use_ssl", port == 465 and not use_tls)
        if use_ssl:
            use_tls = False
        smtp_cls = smtplib.SMTP_SSL if use_ssl else smtplib.SMTP

        with smtp_cls(host, port) as s:
            s.ehlo()
            if use_tls:
                s.starttls()
                s.ehlo()

            auth_err = _auth_smtp(s, cfg)
            if auth_err:
                return False, auth_err, responses, msg_id

            mail_code, mail_resp = s.mail(msg["From"])
            rcpt_responses: dict[str, Any] = {}
            for r in recipients:
                rcpt_code, rcpt_resp = s.rcpt(r)
                rcpt_responses[r] = {
                    "code": rcpt_code,
                    "message": (
                        rcpt_resp.decode()
                        if isinstance(rcpt_resp, bytes)
                        else str(rcpt_resp)
                    ),
                }
            data_code, data_resp = s.data(msg.as_string())
            responses = {
                "mail": {
                    "code": mail_code,
                    "message": (
                        mail_resp.decode()
                        if isinstance(mail_resp, bytes)
                        else str(mail_resp)
                    ),
                },
                "rcpt": rcpt_responses,
                "data": {
                    "code": data_code,
                    "message": (
                        data_resp.decode()
                        if isinstance(data_resp, bytes)
                        else str(data_resp)
                    ),
                },
            }
            success = (
                200 <= mail_code < 300
                and all(200 <= v["code"] < 300 for v in rcpt_responses.values())
                and 200 <= data_code < 300
            )
        return (
            (True, None, responses, msg_id)
            if success
            else (
                False,
                "smtp_error",
                responses,
                msg_id,
            )
        )
    except Exception as exc:
        logging.error("Email send failed: %s", exc.__class__.__name__)
        return False, exc.__class__.__name__


import hashlib
import hmac


# sign_token routine
def sign_token(data: str, secret: str) -> str:
    return hmac.new(secret.encode(), data.encode(), hashlib.sha256).hexdigest()


# verify_token routine
def verify_token(data: str, token: str, secret: str) -> bool:
    expected = sign_token(data, secret)
    return hmac.compare_digest(expected, token)
