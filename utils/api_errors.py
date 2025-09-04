from __future__ import annotations

"""Utilities for standardized API error responses."""

from typing import Any, Mapping

from fastapi.responses import JSONResponse


def error_response(
    code: str,
    message: str,
    *,
    status_code: int = 400,
    details: Mapping[str, Any] | None = None,
) -> JSONResponse:
    """Return a JSONResponse with a standardized error payload.

    Args:
        code: Machine-readable error code.
        message: Human-readable error message.
        status_code: HTTP status code for the response.
        details: Optional additional information about the error.
    """

    payload: dict[str, Any] = {"ok": False, "code": code, "message": message}
    if details:
        payload["details"] = details
    return JSONResponse(payload, status_code=status_code)
