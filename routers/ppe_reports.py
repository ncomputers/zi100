"""PPE report routes."""

from __future__ import annotations

import io
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Dict

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse, RedirectResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from loguru import logger

from config import config
from core.config import ANOMALY_ITEMS
from modules.email_utils import send_email
from modules.report_export import build_ppe_workbook
from modules.utils import require_roles
from schemas.ppe_report import PPEReportQuery
from utils.redis_json import get_json, set_json

router = APIRouter()

BASE_DIR = Path(__file__).resolve().parent.parent


# init_context routine
def init_context(
    config: dict, trackers: Dict[int, "PersonTracker"], redis_client, templates_path
):
    global cfg, trackers_map, redis, templates
    cfg = config
    trackers_map = trackers
    redis = redis_client
    templates = Jinja2Templates(directory=templates_path)


@router.get("/ppe_report")
async def ppe_report_page(request: Request, status: str = "", range: str = ""):
    res = require_roles(request, ["admin"])
    if isinstance(res, RedirectResponse):
        return res
    seen = set()
    statuses = []
    for item in cfg.get("track_ppe", []):
        if item not in seen:
            seen.add(item)
            statuses.append(item)
        anomaly = f"no_{item}"
        if anomaly in ANOMALY_ITEMS and anomaly not in seen:
            seen.add(anomaly)
            statuses.append(anomaly)
    if cfg.get("track_misc", True) and "misc" not in seen:
        seen.add("misc")
        statuses.append("misc")
    no_data = True
    try:
        if redis.zcard("ppe_logs"):
            no_data = False
    except Exception:
        pass
    quick_map = {"7d": "week", "this_month": "month"}
    selected_quick = quick_map.get(range, range)
    return templates.TemplateResponse(
        "ppe_report.html",
        {
            "request": request,
            "cfg": config,
            "status": status,
            "status_options": statuses,
            "no_data": no_data,
            "selected_quick": selected_quick,
        },
    )


@router.get("/ppe_report_data")
async def ppe_report_data(query: PPEReportQuery = Depends()):
    start_ts = int(query.start.timestamp())
    end_ts = int(query.end.timestamp())
    ver = redis.get("ppe_report_version")
    ver = int(ver) if ver else 0
    status_key = ",".join(sorted(query.status)) if query.status else ""
    cache_key = f"ppe_report:{query.start.isoformat()}:{query.end.isoformat()}:{status_key}:{query.min_conf}:{query.color}:{ver}"
    cached = await get_json(redis, cache_key)
    if cached is not None:
        return cached
    entries = [json.loads(e) for e in redis.zrangebyscore("ppe_logs", start_ts, end_ts)]
    rows = []
    thresh = (
        float(query.min_conf)
        if query.min_conf is not None
        else cfg.get("helmet_conf_thresh", 0.5)
    )
    statuses = set(query.status)

    for e in entries:
        ts = e.get("ts")
        if statuses and e.get("status") not in statuses:
            continue
        if e.get("conf", 0) < thresh:
            continue
        if query.color and e.get("color") != query.color:
            continue
        path = e.get("path") or ""
        img_url = ""
        if path:
            fname = os.path.basename(path)
            img_url = f"/snapshots/{fname}"
        rows.append(
            {
                "time": datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M"),
                "cam_id": e.get("cam_id", ""),
                "track_id": e.get("track_id", ""),
                "status": e.get("status", ""),
                "conf": float(e.get("conf", 0)),
                "color": e.get("color") or "",
                "image": img_url,
            }
        )
    data = {"rows": rows}
    try:
        await set_json(redis, cache_key, data, expire=300)
    except Exception:
        pass
    return data


@router.get("/ppe_report/export")
async def ppe_report_export(query: PPEReportQuery = Depends()):
    data = await ppe_report_data(query)
    if "error" in data:
        return JSONResponse(data, status_code=400)
    try:
        wb = build_ppe_workbook(data["rows"])
        bio = io.BytesIO()
        wb.save(bio)
        bio.seek(0)
        headers = {"Content-Disposition": "attachment; filename=ppe_report.xlsx"}
        return StreamingResponse(
            bio,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers=headers,
        )
    except Exception as exc:
        logger.exception("ppe export failed: {}", exc)
        return JSONResponse(
            {"status": "error", "reason": "export_failed"}, status_code=500
        )


@router.post("/ppe_report/email")
async def ppe_report_email(query: PPEReportQuery = Depends(), to: str | None = None):
    data = await ppe_report_data(query)
    if "error" in data:
        return JSONResponse(data, status_code=400)
    wb = build_ppe_workbook(data["rows"])
    bio = io.BytesIO()
    wb.save(bio)
    bio.seek(0)
    recipients = [
        a.strip()
        for a in (to or cfg.get("email", {}).get("from_addr", "")).split(",")
        if a.strip()
    ]
    send_email(
        "PPE Report",
        "See attached report",
        recipients,
        cfg.get("email", {}),
        attachment=bio.getvalue(),
        attachment_name="ppe_report.xlsx",
        attachment_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    return {"sent": True}
