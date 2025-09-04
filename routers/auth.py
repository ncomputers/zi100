"""Authentication routes for user login and session management."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from loguru import logger
from starlette.status import HTTP_302_FOUND

from modules.utils import verify_password
from utils.deps import get_settings, get_templates

router = APIRouter()

logger = logger.bind(module="auth")


@router.get("/login")
async def login_page(
    request: Request,
    cfg: dict = Depends(get_settings),
    templates: Jinja2Templates = Depends(get_templates),
):
    """Render the login page.

    The ``cfg`` object is passed to the template so that branding details such as
    company name and logos can be rendered dynamically.
    """
    return templates.TemplateResponse(
        "login.html",
        {
            "request": request,
            "cfg": cfg,
        },
    )


@router.post("/login")
async def login(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    cfg: dict = Depends(get_settings),
    templates: Jinja2Templates = Depends(get_templates),
):
    try:
        for user in cfg.get("users", []):
            if user["username"] == username and verify_password(
                password, user["password"]
            ):
                request.session["user"] = {
                    "name": username,
                    "role": user.get("role", "viewer"),
                }
                next_url = request.query_params.get("next", "/")
                return RedirectResponse(next_url, status_code=HTTP_302_FOUND)
        return templates.TemplateResponse(
            "login.html",
            {
                "request": request,
                "error": "Invalid credentials",
                "cfg": cfg,
            },
        )
    except Exception:
        logger.bind(username=username).exception("Login failed")
        return templates.TemplateResponse(
            "login.html",
            {"request": request, "error": "Login failed", "cfg": cfg},
            status_code=500,
        )


@router.get("/logout")
async def logout(request: Request, reason: str | None = None):
    """Clear the session and redirect to the login page.

    An optional ``reason`` query parameter is appended to the redirect URL so the
    login template can display contextual messages (e.g. license expired).
    """

    try:
        request.session.pop("user", None)
    except Exception:
        user = request.session.get("user", {}).get("name")
        logger.bind(user=user).exception("Logout failed")
    url = "/login"
    if reason:
        url += f"?reason={reason}"
    return RedirectResponse(url, status_code=HTTP_302_FOUND)
