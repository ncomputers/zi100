"""Miscellaneous utility functions for application modules."""

from __future__ import annotations

import threading
from pathlib import Path

from fastapi import HTTPException, Request
from fastapi.responses import RedirectResponse
from passlib.hash import pbkdf2_sha256
from starlette.status import HTTP_302_FOUND

from config import config as app_config

SNAP_DIR = Path(__file__).resolve().parent.parent / "snapshots"
SNAP_DIR.mkdir(exist_ok=True)

# Global lock used by tracker manager to synchronize frame access
lock = threading.Lock()


# hash_password routine
def hash_password(password: str) -> str:
    """Hash a password using PBKDF2."""
    return pbkdf2_sha256.hash(password)


# verify_password routine
def verify_password(password: str, hashed: str) -> bool:
    """Verify a password against a hash."""
    if hashed.startswith("$pbkdf2-sha256$"):
        return pbkdf2_sha256.verify(password, hashed)
    return password == hashed


# require_roles routine
def require_roles(request: Request, roles: list[str]):
    """Ensure the current session user has one of ``roles``.

    Also checks the global license status. If the license is missing or
    expired, the user is logged out and redirected to the login page with a
    ``reason=license`` query parameter so the UI can display an appropriate
    message.
    """

    lic = app_config.get("license_info")
    # Access session data safely for real Request objects and simple test doubles
    scope = getattr(request, "scope", None)
    if isinstance(scope, dict) and "session" in scope:
        session = scope.get("session")
    else:
        session = getattr(request, "session", {})

    if lic and lic.get("valid") is False:
        if isinstance(session, dict):
            session.pop("user", None)
        return RedirectResponse("/login?reason=license", status_code=HTTP_302_FOUND)

    user = session.get("user") if isinstance(session, dict) else None
    if not user or user.get("role") not in roles:
        return RedirectResponse("/login", status_code=HTTP_302_FOUND)
    return user


# require_admin routine
def require_admin(request: Request):
    """Dependency that ensures the current session user has the ``admin`` role."""
    res = require_roles(request, ["admin"])
    if isinstance(res, RedirectResponse):
        raise HTTPException(status_code=HTTP_302_FOUND, headers={"Location": "/login"})
    return res


# require_viewer routine
def require_viewer(request: Request):
    """Dependency that permits users with ``viewer`` or ``admin`` roles."""
    res = require_roles(request, ["viewer", "admin"])
    if isinstance(res, RedirectResponse):
        raise HTTPException(status_code=HTTP_302_FOUND, headers={"Location": "/login"})
    return res
