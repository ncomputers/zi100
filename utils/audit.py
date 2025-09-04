"""Simple audit trail logging utilities."""

from __future__ import annotations

from typing import Any

from loguru import logger


def log_audit(action: str, user: str, reason: str | None = None, **details: Any) -> None:
    """Write an audit entry with ``action``, ``user``, and optional ``reason``.

    Additional keyword arguments may be supplied in ``details``.
    """
    payload: dict[str, Any] = {"action": action, "user": user}
    if reason:
        payload["reason"] = reason
    if details:
        payload.update(details)
    logger.bind(audit=True, **payload).info("audit")
