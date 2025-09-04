"""Email and alert rule management routes."""

from __future__ import annotations

import json
import os

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from fastapi_csrf_protect import CsrfProtect
from loguru import logger
from pydantic import ValidationError
from pydantic_settings import BaseSettings

from config import config
from core import events
from core.config import ANOMALY_ITEMS, save_config
from modules.utils import require_roles
from schemas.alerts import AlertRule
from utils.deps import get_config_path, get_redis, get_settings, get_templates

router = APIRouter()

logger = logger.bind(module="alerts")


class CsrfSettings(BaseSettings):
    secret_key: str


@CsrfProtect.load_config
def get_csrf_config() -> CsrfSettings:
    """Provide CSRF settings using environment or config values."""
    secret = os.getenv("CSRF_SECRET_KEY") or config.get("secret_key", "change-me")
    return CsrfSettings(secret_key=secret)


csrf_protect = CsrfProtect()


@router.get("/alerts")
async def alerts_page(
    request: Request,
    cfg: dict = Depends(get_settings),
    templates: Jinja2Templates = Depends(get_templates),
):
    """Render the email alerts configuration page."""
    res = require_roles(request, ["admin"])
    if isinstance(res, RedirectResponse):
        return res
    items = list(ANOMALY_ITEMS) + sorted(events.ALL_EVENTS)
    token, signed = csrf_protect.generate_csrf_tokens()
    # Render the template immediately so tests can access ``response.body``
    html = templates.get_template("email_alerts.html").render(
        {
            "request": request,
            "rules": cfg.get("alert_rules", []),
            "anomaly_items": items,
            "cfg": cfg,
            "csrf_token": token,
        }
    )
    response = HTMLResponse(html)
    csrf_protect.set_csrf_cookie(signed, response)
    return response


@router.post("/alerts")
async def save_alerts(
    request: Request,
    cfg: dict = Depends(get_settings),
    redis=Depends(get_redis),
    cfg_path: str = Depends(get_config_path),
):
    """Persist alert rule updates from the settings form."""
    res = require_roles(request, ["admin"])
    if isinstance(res, RedirectResponse):
        return res
    data = await request.json()
    rules_data = data.get("rules", [])
    allowed = set(ANOMALY_ITEMS) | events.ALL_EVENTS
    AlertRule.allowed_metrics = allowed
    validated = []
    for r in rules_data:
        try:
            rule = AlertRule.model_validate(r)
        except ValidationError as exc:
            raise HTTPException(status_code=400, detail=json.loads(exc.json()))
        rd = rule.model_dump()
        rd["recipients"] = ",".join(rd["recipients"])
        validated.append(rd)
    cfg["alert_rules"] = validated
    try:
        save_config(cfg, cfg_path, redis)
    except Exception:
        user = request.session.get("user", {}).get("name")
        logger.bind(user=user).exception("Failed to save alert rules")
        raise HTTPException(status_code=500, detail="save_failed")
    return {"saved": True}
