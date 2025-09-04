from __future__ import annotations

"""Gatepass reporting and view routes."""

import json
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from loguru import logger

from config import config as cfg
from modules import export
from utils.time import format_ts

from . import (
    _format_gatepass_times,
    _load_gatepass,
    _qr_data_uri,
    _sanitize_placeholders,
    config_obj,
    gatepass_service,
    parse_timestamp,
    redis,
    templates,
)

router = APIRouter()


def format_gatepass_record(rec: dict, gate_id: str) -> dict:
    """Return gate pass record with formatted fields and signature URL."""

    _format_gatepass_times(rec)
    _sanitize_placeholders(rec)

    signature_url = rec.get("signature")
    if signature_url:
        if not signature_url.startswith("/"):
            signature_url = "/" + signature_url
    else:
        sig_file = Path("static/signatures") / f"{gate_id}.png"
        if sig_file.exists():
            signature_url = f"/static/signatures/{gate_id}.png"

    if signature_url:
        rec["signature"] = signature_url
    rec["signature_url"] = signature_url
    return rec


@router.get("/gatepass/card/{gate_id}")
async def gatepass_card(gate_id: str, request: Request):
    """Render digital gate pass page."""
    if not config_obj.get("features", {}).get("visitor_mgmt"):
        return RedirectResponse("/", status_code=302)
    try:
        item = _load_gatepass(gate_id)
    except RuntimeError:
        return HTMLResponse("redis_unavailable", status_code=503)
    if not item:
        logger.warning(f"Gate pass not found: {gate_id}")
        return HTMLResponse("<h3>Gate pass not found</h3>", status_code=404)
    item = format_gatepass_record(item, gate_id)
    branding = config_obj.get("branding", {})
    org = branding.get("company_name", "")
    site = branding.get("site_name", "")
    color_map = {
        "pending": "warning text-dark",
        "approved": "success",
        "rejected": "danger",
        "created": "secondary",
    }
    status_color = color_map.get(item.get("status", "created"), "secondary")
    photo_url = (
        f"data:image/jpeg;base64,{item['image']}"
        if item.get("image") and not item.get("no_photo")
        else ""
    )
    qr_img = _qr_data_uri(gatepass_service.build_qr_link(gate_id, request))
    card = {
        **item,
        "status_color": status_color,
        "photo_url": photo_url,
    }
    return templates.TemplateResponse(
        "gatepass_card.html",
        {
            "request": request,
            "card": card,
            "cfg": config_obj,
            "org": org,
            "site": site,
            "mode": "view",
        },
    )


@router.get("/gatepass/print/{gate_id}")
async def gatepass_print(gate_id: str, request: Request, pdf: bool = False):
    """Render printable gate pass page."""
    if not config_obj.get("features", {}).get("visitor_mgmt"):
        return RedirectResponse("/", status_code=302)
    try:
        item = _load_gatepass(gate_id)
    except RuntimeError:
        return HTMLResponse("redis_unavailable", status_code=503)
    if not item:
        return HTMLResponse("not found", status_code=404)
    item = format_gatepass_record(item, gate_id)
    branding = config_obj.get("branding", {})
    org = branding.get("company_name", "")
    site = branding.get("site_name", "")
    color_map = {
        "pending": "warning text-dark",
        "approved": "success",
        "rejected": "danger",
        "created": "secondary",
        "Meeting in progress": "info",
        "Completed": "success",
    }
    status_color = color_map.get(item.get("status", "created"), "secondary")
    photo_url = (
        f"data:image/jpeg;base64,{item['image']}"
        if item.get("image") and not item.get("no_photo")
        else ""
    )
    qr_img = _qr_data_uri(gatepass_service.build_qr_link(gate_id, request))
    card = {
        **item,
        "status_color": status_color,
        "photo_url": photo_url,
    }
    layout = config_obj.get("branding", {}).get("print_layout", "A5")
    context = {
        "request": request,
        "card": card,
        "cfg": config_obj,
        "org": org,
        "site": site,
        "mode": "print",
        "gate_id": gate_id,
        "print_layout": layout,
        "qr_img": qr_img,
    }
    if pdf:
        html = templates.get_template("gatepass_print.html").render(
            **context, show_controls=False
        )
        return export.export_pdf(html, f"gatepass_{gate_id}")

    return templates.TemplateResponse("gatepass_print.html", context)


@router.get("/gatepass/view/{gate_id}")
async def gatepass_view(gate_id: str, request: Request):
    """Render digital gate pass page."""
    if not config_obj.get("features", {}).get("visitor_mgmt"):
        return HTMLResponse("visitor_mgmt_disabled", status_code=404)
    try:
        item = _load_gatepass(gate_id)
    except RuntimeError:
        return HTMLResponse("redis_unavailable", status_code=503)
    if not item:
        return HTMLResponse("<h3>Gate pass not found</h3>", status_code=404)
    item = format_gatepass_record(item, gate_id)
    branding = config_obj.get("branding", {})
    org = branding.get("company_name", "")
    site = branding.get("site_name", "")
    color_map = {
        "pending": "warning text-dark",
        "approved": "success",
        "rejected": "danger",
        "created": "secondary",
        "Meeting in progress": "info",
        "Completed": "success",
    }
    status_color = color_map.get(item.get("status", "created"), "secondary")
    photo_url = (
        f"data:image/jpeg;base64,{item['image']}"
        if item.get("image") and not item.get("no_photo")
        else ""
    )
    qr_img = _qr_data_uri(gatepass_service.build_qr_link(gate_id, request))
    card = {
        **item,
        "status_color": status_color,
        "photo_url": photo_url,
    }
    return templates.TemplateResponse(
        "gatepass_view.html",
        {
            "request": request,
            "card": card,
            "cfg": config_obj,
            "org": org,
            "site": site,
            "mode": "view",
            "qr_img": qr_img,
        },
    )


@router.get("/gatepass/list")
async def gatepass_list(request: Request):
    """Render table view of all saved gate passes."""
    if not config_obj.get("features", {}).get("visitor_mgmt"):
        return RedirectResponse("/", status_code=302)
    try:
        entries = redis.zrevrange("vms_logs", 0, -1)
    except Exception:
        logger.exception("Redis unavailable while listing gate passes")
        return HTMLResponse("redis_unavailable", status_code=503)
    rows = []
    for e in entries:
        obj = json.loads(e)
        ts = parse_timestamp(obj.get("ts"))
        if ts is not None:
            obj["ts"] = ts
            obj["time"] = format_ts(ts)
        vt = parse_timestamp(obj.get("valid_to"))
        if vt is not None:
            obj["valid_to"] = vt
            obj["valid_to_str"] = format_ts(vt)
        rows.append(obj)
    return templates.TemplateResponse(
        "gatepass_list.html",
        {
            "request": request,
            "rows": rows,
            "cfg": cfg,
            "build_qr_link": gatepass_service.build_qr_link,
        },
    )


@router.get("/gatepass/export")
async def gatepass_export(fmt: str = "csv"):
    """Export gate pass history."""
    try:
        entries = redis.zrevrange("vms_logs", 0, -1)
    except Exception:
        logger.exception("Redis unavailable while exporting gate passes")
        return JSONResponse({"error": "redis_unavailable"}, status_code=503)
    rows = [json.loads(e) for e in entries]
    for r in rows:
        r["time"] = format_ts(r["ts"])
        if r.get("valid_to"):
            r["valid_to_str"] = format_ts(r["valid_to"])
    columns = [
        ("gate_id", "Gate ID"),
        ("name", "Name"),
        ("phone", "Phone"),
        ("host", "Host"),
        ("purpose", "Purpose"),
        ("time", "Created"),
        ("valid_to_str", "Valid To"),
        ("status", "Status"),
    ]
    if fmt == "xlsx":
        return export.export_excel(rows, columns, "gate_passes")
    if fmt == "pdf":
        html = (
            "<table><tr>"
            + "".join(f"<th>{c[1]}</th>" for c in columns)
            + "</tr>"
            + "".join(
                "<tr>"
                + "".join(f"<td>{row.get(c[0],'')}</td>" for c in columns)
                + "</tr>"
                for row in rows
            )
            + "</table>"
        )
        return export.export_pdf(html, "gate_passes")
    return export.export_csv(rows, columns, "gate_passes")
