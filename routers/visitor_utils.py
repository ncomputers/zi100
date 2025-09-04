"""Helpers for visitor management routes.

Defines canonical error messaging used when the visitor management feature is
disabled or not licensed.  Importing modules can use these helpers to ensure
consistent responses across the application.
"""

from types import SimpleNamespace

from fastapi import HTTPException
from fastapi.responses import JSONResponse

# Canonical message used whenever visitor management is unavailable.
VISITOR_DISABLED_MSG = (
    "Visitor management feature disabled; enable in settings or license"
)


def visitor_disabled_response() -> JSONResponse:
    """Return a standardized 403 response for disabled visitor management."""
    return JSONResponse({"error": VISITOR_DISABLED_MSG}, status_code=403)


def require_visitor_mgmt() -> SimpleNamespace:
    """Dependency enforcing visitor management feature availability."""
    from .visitor import get_context

    ctx = get_context()
    if not ctx.config.get("features", {}).get("visitor_mgmt"):
        raise HTTPException(status_code=403, detail=VISITOR_DISABLED_MSG)
    return ctx


__all__ = [
    "visitor_disabled_response",
    "VISITOR_DISABLED_MSG",
    "require_visitor_mgmt",
]
