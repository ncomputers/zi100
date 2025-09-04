"""Visit request management routes."""

from __future__ import annotations

import json
import time
from datetime import datetime

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse
from loguru import logger

from config import config
from modules import export
from modules.email_utils import send_email
from modules.utils import require_admin
from utils.ids import generate_id
from utils.redis import trim_sorted_set

from . import get_context

ctx = get_context()
config_obj = ctx.config
redis = ctx.redis
templates = ctx.templates

router = APIRouter()


def require_visitor_mgmt() -> None:
    if not config_obj.get("features", {}).get("visitor_mgmt"):
        logger.error("visitor management disabled")
        raise HTTPException(status_code=403, detail="visitor management disabled")


@router.get("/visit_requests/pending", dependencies=[Depends(require_visitor_mgmt)])
async def visit_requests_page(request: Request, user=Depends(require_admin)):
    if redis is None:
        logger.error("visit requests page unavailable: redis connection missing")
        raise HTTPException(status_code=503, detail="redis_unavailable")
    entries = redis.zrevrange("visit_requests", 0, -1)
    rows = []
    for e in entries:
        obj = json.loads(e)
        if obj.get("status") != "pending":
            continue
        obj["time"] = datetime.fromtimestamp(obj["ts"]).isoformat(
            sep=" ", timespec="seconds"
        )
        rows.append(obj)
    return templates.TemplateResponse(
        "visit_requests.html", {"request": request, "rows": rows, "cfg": config}
    )


# _update_request routine
async def _update_request(req_id: str, new_status: str, extra: dict | None = None):
    allowed = {"approved", "rejected", "pending", "waiting", "rescheduled"}
    if new_status not in allowed:
        raise ValueError("invalid_status")
    if redis is None:
        raise HTTPException(status_code=503, detail="redis_unavailable")
    entries = redis.zrevrange("visit_requests", 0, -1)
    for e in entries:
        obj = json.loads(e)
        if obj["id"] == req_id:
            obj["status"] = new_status
            if extra:
                obj.update(extra)
            redis.zadd("visit_requests", {json.dumps(obj): obj["ts"]})
            await trim_sorted_set(redis, "visit_requests", obj["ts"])
            return obj
    return None


async def _approve_request(req_id: str) -> dict | None:
    """Mark a visit request as approved."""
    return await _update_request(req_id, "approved")


def _create_gatepass(obj: dict, request: Request) -> tuple[dict, bytes]:
    """Generate a gatepass entry and associated PDF."""

    from routers import gatepass

    gate_id = f"GP{generate_id()[:8].upper()}"
    ts = int(time.time())
    entry = {
        "gate_id": gate_id,
        "ts": ts,
        "name": obj.get("name", ""),
        "phone": obj.get("phone", ""),
        "email": obj.get("email", ""),
        "host": obj.get("host", ""),
        "visitor_type": obj.get("visitor_type", ""),
        "company_name": obj.get("company", ""),
        "status": "approved",
        "image": obj.get("image", ""),
        "valid_from": ts,
        "valid_to": ts + 24 * 60 * 60,
        "qr": gatepass.gatepass_service.build_qr_link(gate_id, request),
    }
    qr_img = gatepass._qr_data_uri(entry["qr"])
    obj["gate_id"] = gate_id
    pdf_bytes = b""
    try:
        gatepass._save_gatepass(entry)
        branding = config.get("branding", {})
        org = branding.get("company_name")
        site = branding.get("site_name")
        layout = branding.get("print_layout", "A5")
        context = {
            "card": entry,
            "cfg": config,
            "org": org,
            "site": site,
            "mode": "pdf",
            "gate_id": gate_id,
            "show_controls": False,
            "print_layout": layout,
            "qr_img": qr_img,
        }
        html = gatepass.templates.get_template("gatepass_print.html").render(**context)
        result = export.export_pdf(html, f"gatepass_{gate_id}")
        if not isinstance(result, dict):
            pdf_path = export.EXPORT_DIR / f"gatepass_{gate_id}.pdf"
            pdf_bytes = pdf_path.read_bytes()
    except Exception:
        logger.exception("gatepass generation failed for {}", obj.get("id"))
    return entry, pdf_bytes


def _send_approval_email(obj: dict, pdf_bytes: bytes) -> None:
    if obj.get("email"):
        send_email(
            "Visit Approved",
            "Your visit has been approved.",
            [obj["email"]],
            config_obj.get("email", {}),
            attachment=pdf_bytes or None,
            attachment_name=f"gatepass_{obj.get('gate_id')}.pdf" if pdf_bytes else None,
            attachment_type="application/pdf" if pdf_bytes else None,
        )


@router.post("/visit_requests/approve", dependencies=[Depends(require_visitor_mgmt)])
async def approve_request(request: Request, id: str = Form(...)):
    obj = await _approve_request(id)
    if obj:
        _, pdf_bytes = _create_gatepass(obj, request)
        _send_approval_email(obj, pdf_bytes)
    return {"ok": True}


@router.post("/visit_requests/wait", dependencies=[Depends(require_visitor_mgmt)])
async def wait_request(id: str = Form(...)):
    await _update_request(id, "waiting")
    return {"ok": True}


@router.post(
    "/visit_requests/reschedule",
    dependencies=[Depends(require_visitor_mgmt)],
)
async def reschedule_request(id: str = Form(...), new_time: str = Form(...)):
    await _update_request(id, "rescheduled", {"reschedule_time": new_time})
    return {"ok": True}


@router.post("/visit_requests/reject", dependencies=[Depends(require_visitor_mgmt)])
async def reject_request(id: str = Form(...)):
    await _update_request(id, "rejected")
    return {"ok": True}


@router.get("/visit_requests/export", dependencies=[Depends(require_visitor_mgmt)])
async def visit_request_export(status: str = ""):
    """Export visit requests with optional status filter."""
    if redis is None:
        raise HTTPException(status_code=503, detail="redis_unavailable")
    entries = redis.zrevrange("visit_requests", 0, -1)
    rows = []
    for e in entries:
        obj = json.loads(e)
        if status and obj.get("status") != status:
            continue
        obj["time"] = datetime.fromtimestamp(obj["ts"]).isoformat(
            sep=" ", timespec="seconds"
        )
        rows.append(obj)
    columns = [
        ("id", "ID"),
        ("name", "Name"),
        ("phone", "Phone"),
        ("visitor_type", "Visitor Type"),
        ("company", "Company"),
        ("host", "Host"),
        ("status", "Status"),
        ("time", "Time"),
    ]
    return export.export_csv(rows, columns, "visit_requests")


@router.get(
    "/visit_requests/approve_link/{req_id}",
    dependencies=[Depends(require_visitor_mgmt)],
)
async def approve_request_link(req_id: str):
    """Approve a visit request via direct link."""
    obj = await _update_request(req_id, "approved")
    if obj and obj.get("email"):
        send_email(
            "Visit Approved",
            "Your visit has been approved.",
            [obj["email"]],
            config_obj.get("email", {}),
        )
    return HTMLResponse(
        "approved" if obj else "invalid", status_code=200 if obj else 404
    )
