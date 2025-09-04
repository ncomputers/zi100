from __future__ import annotations

"""Gatepass approval and notification routes."""

import hmac
import json
import time
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse
from loguru import logger

from config import config as cfg
from modules.email_utils import send_email, sign_token

from . import (
    _cache_gatepass,
    _load_gatepass,
    gatepass_service,
    config_obj,
    redis,
    templates,
)

router = APIRouter()


@router.get("/gatepass/approve", name="gatepass_approve")
async def gatepass_approve(token: str, request: Request) -> HTMLResponse:
    try:
        gp_id, sig = token.split(":", 1)
    except ValueError:
        return HTMLResponse("invalid token", status_code=400)
    stored_sig = redis.get(f"gatepass:signature:{gp_id}")
    if isinstance(stored_sig, bytes):
        stored_sig = stored_sig.decode()
    if not stored_sig or not hmac.compare_digest(stored_sig, sig):
        return HTMLResponse("invalid token", status_code=400)
    obj = _load_gatepass(gp_id)
    if obj:
        obj["status"] = "approved"
        redis.zadd("vms_logs", {json.dumps(obj): int(obj["ts"])})
        _cache_gatepass(obj)
        return templates.TemplateResponse(
            "gatepass_confirm.html", {"request": request, "status": "approved"}
        )
    return HTMLResponse("not found", status_code=404)


@router.get("/gatepass/reject", name="gatepass_reject")
async def gatepass_reject(token: str, request: Request) -> HTMLResponse:
    try:
        gp_id, sig = token.split(":", 1)
    except ValueError:
        return HTMLResponse("invalid token", status_code=400)
    stored_sig = redis.get(f"gatepass:signature:{gp_id}")
    if isinstance(stored_sig, bytes):
        stored_sig = stored_sig.decode()
    if not stored_sig or not hmac.compare_digest(stored_sig, sig):
        return HTMLResponse("invalid token", status_code=400)
    obj = _load_gatepass(gp_id)
    if obj:
        obj["status"] = "rejected"
        redis.zadd("vms_logs", {json.dumps(obj): int(obj["ts"])})
        _cache_gatepass(obj)
        return templates.TemplateResponse(
            "gatepass_confirm.html", {"request": request, "status": "rejected"}
        )
    return HTMLResponse("not found", status_code=404)


@router.get("/pending-requests")
async def pending_requests(request: Request):
    entries = redis.zrevrange("vms_logs", 0, -1)
    rows = []
    for e in entries:
        obj = json.loads(e)
        if obj.get("status") == "pending":
            obj["time"] = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(obj["ts"]))
            rows.append(obj)
    return templates.TemplateResponse(
        "pending_requests.html",
        {
            "request": request,
            "rows": rows,
            "cfg": cfg,
            "build_qr_link": gatepass_service.build_qr_link,
        },
    )


@router.post("/gatepass/resend/{gp_id}")
async def gatepass_resend(gp_id: str) -> JSONResponse:
    try:
        obj = _load_gatepass(gp_id)
    except RuntimeError:
        return JSONResponse({"error": "redis_unavailable"}, status_code=503)
    if obj and obj.get("status") == "pending":
        email = obj.get("approver_email")
        if email:
            base = config_obj.get("base_url", "").rstrip("/")
            tok = f"{gp_id}:{sign_token(gp_id, config_obj.get('secret_key', 'secret'))}"
            approve_url = f"{base}/gatepass/approve?token={tok}"
            reject_url = f"{base}/gatepass/reject?token={tok}"
            msg = (
                f"<p>Gate pass for {obj.get('name','')} requires approval.</p>"
                f"<p><a href='{approve_url}'>Approve</a> | <a href='{reject_url}'>Reject</a></p>"
            )
            send_email(
                "Gate Pass Approval",
                msg,
                [email],
                config_obj.get("email", {}),
                html=True,
            )
        return JSONResponse({"resent": True})
    return JSONResponse({"error": "not_found"}, status_code=404)


@router.post("/gatepass/cancel/{gp_id}")
async def gatepass_cancel(gp_id: str) -> JSONResponse:
    try:
        obj = _load_gatepass(gp_id)
    except RuntimeError:
        return JSONResponse({"error": "redis_unavailable"}, status_code=503)
    if obj:
        obj["status"] = "rejected"
        try:
            redis.zadd("vms_logs", {json.dumps(obj): int(obj["ts"])})
            _cache_gatepass(obj)
        except Exception:
            logger.exception("Redis unavailable while cancelling gate pass {}", gp_id)
            return JSONResponse({"error": "redis_unavailable"}, status_code=503)
        return JSONResponse({"cancelled": True})
    return JSONResponse({"error": "not_found"}, status_code=404)
