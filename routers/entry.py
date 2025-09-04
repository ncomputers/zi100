"""Routes for visitor management entry operations."""

from __future__ import annotations

import base64
import json
import time
from datetime import datetime
from typing import Annotated, Optional

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    Request,
    UploadFile,
)
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from loguru import logger
from pydantic import BaseModel

import routers.visitor as visitor
from config import config as cfg
from modules import export, gatepass_service, visitor_db
from modules.email_utils import send_email
from modules.utils import require_roles
from utils.ids import generate_id
from utils.image import decode_base64_image
from utils.redis import trim_sorted_set_async as trim_sorted_set


from .entry_stats import (
    collect_logs,
    compute_avg_duration,
    compute_busiest_day,
    compute_daily_counts,
    compute_occupancy,
    compute_peak_hour,
    compute_returning_pct,
    compute_top_counts,
    get_total_invites,
)
from .visitor_utils import visitor_disabled_response

router = APIRouter()


class RegisterVisitorForm(BaseModel):
    """Form data for the visitor registration endpoint."""

    name: str
    phone: str = ""
    visitor_id: str = ""
    host: str = ""
    purpose: str = ""
    visitor_type: str = ""
    captured: str = ""
    valid_to: str = ""

    @classmethod
    def as_form(
        cls,
        name: str = Form(...),
        phone: str = Form(""),
        visitor_id: str = Form(""),
        host: str = Form(""),
        purpose: str = Form(""),
        visitor_type: str = Form(""),
        captured: str = Form(""),
        valid_to: str = Form(""),
    ) -> "RegisterVisitorForm":
        return cls(
            name=name,
            phone=phone,
            visitor_id=visitor_id,
            host=host,
            purpose=purpose,
            visitor_type=visitor_type,
            captured=captured,
            valid_to=valid_to,
        )


# init_context routine
def init_context(cfg_obj: dict, redis_client, templates_path: str) -> None:
    global config_obj, redis, templates, face_app
    config_obj = cfg_obj
    redis = redis_client
    templates = Jinja2Templates(directory=templates_path)
    face_app = None
    visitor_db.init_db(redis_client)
    visitor.redis = redis_client
    try:
        from insightface.app import FaceAnalysis  # type: ignore

        face_app = FaceAnalysis(name=cfg_obj.get("visitor_model", "buffalo_l"))
        face_app.prepare(ctx_id=0)
    except Exception:
        face_app = None


@router.get("/vms/recent")
async def vms_recent(request: Request):

    res = require_roles(request, ["admin", "viewer"])
    if isinstance(res, RedirectResponse):
        return res
    try:
        entries = redis.zrevrange("vms_logs", 0, 49)
    except Exception as exc:  # pragma: no cover - network failure
        logger.exception("Redis unavailable: {}", exc)
        entries = []
    rows: list[dict] = []
    for e in entries:
        obj = json.loads(e)
        obj["time"] = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(obj["ts"]))
        if obj.get("valid_to"):
            obj["valid_to_str"] = time.strftime(
                "%Y-%m-%d %H:%M:%S", time.localtime(obj["valid_to"])
            )
        rows.append(obj)
    return rows


@router.get("/vms")
async def vms_page(request: Request, req_id: str | None = None):

    res = require_roles(request, ["admin", "viewer"])
    if isinstance(res, RedirectResponse):
        return res
    if not config_obj.get("features", {}).get("visitor_mgmt"):
        return RedirectResponse("/", status_code=302)
    rows: list = []

    prefill = None
    if req_id:
        try:
            reqs = redis.zrevrange("visit_requests", 0, -1)
        except Exception as exc:  # pragma: no cover - network failure
            logger.exception("Redis unavailable: {}", exc)
            reqs = []
        for e in reqs:
            obj = json.loads(e)
            if obj.get("id") == req_id:
                prefill = obj
                break
    return templates.TemplateResponse(
        "vms.html", {"request": request, "rows": rows, "cfg": cfg, "prefill": prefill}
    )


@router.get("/vms/create")
async def vms_create_page(request: Request, req_id: str | None = None):
    """Dedicated page to generate a new gate pass."""
    res = require_roles(request, ["admin", "viewer"])
    if isinstance(res, RedirectResponse):
        return res
    if not config_obj.get("features", {}).get("visitor_mgmt"):
        return RedirectResponse("/", status_code=302)
    prefill = None
    if req_id:
        try:
            reqs = redis.zrevrange("visit_requests", 0, -1)
        except Exception as exc:  # pragma: no cover - network failure
            logger.exception("Redis unavailable: {}", exc)
            reqs = []
        for e in reqs:
            obj = json.loads(e)
            if obj.get("id") == req_id:
                prefill = obj
                break
    return templates.TemplateResponse(
        "vms_create.html",
        {
            "request": request,
            "cfg": cfg,
            "prefill": prefill,
            "now": datetime.utcnow().strftime("%Y-%m-%dT%H:%M"),
            "qr_base": gatepass_service.build_qr_link("", request),
        },
    )


async def _parse_visitor_form(
    form: RegisterVisitorForm, photo: Optional[UploadFile]
) -> dict:
    b64 = ""
    img_bytes = None
    if form.captured:
        try:
            img_bytes = decode_base64_image(form.captured)
        except ValueError as exc:
            raise HTTPException(
                status_code=400, detail="Invalid captured image data"
            ) from exc
    if photo and not img_bytes:
        img_bytes = await photo.read()
    if img_bytes:
        b64 = base64.b64encode(img_bytes).decode()
    ts = int(time.time())
    face_id = generate_id()
    valid_from = ts
    try:
        valid_to_ts = (
            int(datetime.fromisoformat(form.valid_to).timestamp())
            if form.valid_to
            else ts
        )
    except Exception:
        valid_to_ts = ts
    vid = (
        form.visitor_id
        if isinstance(form.visitor_id, str) and form.visitor_id
        else visitor_db.get_or_create_visitor(form.name, form.phone, photo=b64)
    )
    entry = {
        "gate_id": f"GP{ts}",
        "face_id": face_id,
        "visitor_id": vid,
        "name": form.name,
        "phone": form.phone,
        "host": form.host,
        "purpose": form.purpose,
        "visitor_type": form.visitor_type,
        "status": "created",
        "ts": ts,
        "image": b64,
        "valid_from": valid_from,
        "valid_to": valid_to_ts,
    }
    redis.zadd("vms_logs", {json.dumps(entry): ts})
    await trim_sorted_set(redis, "vms_logs", ts)
    if form.host:
        visitor_db.save_host(form.host, "")
    return {"entry": entry, "img_bytes": img_bytes}


async def _update_visit_request(
    redis_client, form: RegisterVisitorForm, gate_id: str
) -> None:
    reqs = redis_client.zrevrange("visit_requests", 0, -1)
    for r in reqs:
        obj = json.loads(r)
        if obj.get("phone") == form.phone and obj.get("status") in [
            "approved",
            "pending",
        ]:
            obj["status"] = "arrived"
            obj["gate_id"] = gate_id
            redis_client.zadd("visit_requests", {json.dumps(obj): obj["ts"]})
            await trim_sorted_set(redis_client, "visit_requests", obj["ts"])
            if obj.get("email"):
                send_email(
                    "Visitor Arrived",
                    f"{form.name} has arrived",
                    [obj["email"]],
                    cfg.get("email", {}),
                )
            break


def _add_face_to_db(img_bytes: bytes | None, gate_id: str) -> None:
    if not img_bytes:
        return
    try:
        from modules import face_db

        added = face_db.add_face_if_single_detected(img_bytes, gate_id, threshold=1.1)
        if not added:
            logger.warning(f"No face detected for entry {gate_id}")
    except Exception as exc:  # pragma: no cover - defensive
        logger.exception("Error adding face for entry {}: {}", gate_id, exc)


@router.post("/vms/register")
async def register_visitor(
    form: RegisterVisitorForm = Depends(RegisterVisitorForm.as_form),
    photo: Optional[UploadFile] = File(None),
    **data,
):
    if not isinstance(form, RegisterVisitorForm):
        form = RegisterVisitorForm(**data)
    if redis is None:
        raise HTTPException(status_code=500, detail="Redis client not initialized")
    if not config_obj.get("features", {}).get("visitor_mgmt"):
        return visitor_disabled_response()
    parsed = await _parse_visitor_form(form, photo)
    entry = parsed["entry"]
    img_bytes = parsed["img_bytes"]
    await _update_visit_request(redis, form, entry["gate_id"])
    _add_face_to_db(img_bytes, entry["gate_id"])
    return {
        "saved": True,
        "gate_id": entry["gate_id"],
        "time": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(entry["ts"])),
    }


@router.get("/vms/export")
async def export_vms(fmt: str = "csv"):
    if not config_obj.get("features", {}).get("visitor_mgmt"):
        return RedirectResponse("/", status_code=302)
    try:
        entries = redis.zrevrange("vms_logs", 0, -1)
        rows = [json.loads(e) for e in entries]
        for r in rows:
            r["time"] = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(r["ts"]))
            if r.get("valid_to"):
                r["valid_to_str"] = time.strftime(
                    "%Y-%m-%d %H:%M:%S", time.localtime(r["valid_to"])
                )
        columns = [
            ("gate_id", "Gate ID"),
            ("name", "Name"),
            ("phone", "Phone"),
            ("host", "Host"),
            ("visitor_type", "Type"),
            ("purpose", "Purpose"),
            ("time", "Time"),
            ("valid_to_str", "Valid To"),
        ]
        if fmt == "xlsx":
            for r in rows:
                if r.get("image"):
                    import base64 as b64
                    import os
                    import uuid as uuid_mod

                    img_path = f"static/exports/{uuid_mod.uuid4().hex}.jpg"
                    with open(img_path, "wb") as f:
                        f.write(b64.b64decode(r["image"]))
                    r["img_path"] = img_path
            resp = export.export_excel(
                rows, columns, "gate_pass_history", image_key="img_path"
            )
            for r in rows:
                p = r.get("img_path")
                if p:
                    try:
                        os.remove(p)
                    except Exception:
                        pass
            return resp
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
            return export.export_pdf(html, "gate_pass_history")
        return export.export_csv(rows, columns, "gate_pass_history")
    except Exception as exc:
        logger.exception("vms export failed: {}", exc)
        return JSONResponse(
            {"status": "error", "reason": "export_failed"}, status_code=500
        )


@router.get("/api/vms/stats")
async def vms_stats(
    request: Request = None,
    range_: Annotated[str, Query(alias="range")] = "7d",
):
    """Return aggregated visitor metrics for dashboard widgets."""
    if not config_obj.get("features", {}).get("visitor_mgmt"):
        return visitor_disabled_response()
    try:
        now = int(time.time())
        tf = (range_ if isinstance(range_, str) else range_.default).lower()
        today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        if tf in ["today", "1d"]:
            start_ts = int(today.timestamp())
        elif tf.startswith("30") or tf.startswith("month"):
            start_ts = now - 30 * 86400
        elif tf in ["this_month", "month_curr"]:
            start_ts = int(today.replace(day=1).timestamp())
        elif tf in ["this_year", "year"]:
            start_ts = int(today.replace(month=1, day=1).timestamp())
        else:  # default last 7 days
            start_ts = now - 7 * 86400

        redis_client = (
            getattr(request.app.state, "redis_client", redis) if request else redis
        )

        logs = collect_logs(redis_client, start_ts, now)
        result = {
            "occupancy": compute_occupancy(logs, now),
            "peak_hour": compute_peak_hour(logs),
            "total_invites": get_total_invites(redis_client),
            "busiest_day": compute_busiest_day(logs),
            "avg_duration": compute_avg_duration(logs),
            "returning_pct": compute_returning_pct(logs),
            "visitor_daily": compute_daily_counts(logs, start_ts, now),
            "top_employees": compute_top_counts(logs, "host"),
            "top_visitors": compute_top_counts(logs, "name"),
            "purpose_counts": compute_top_counts(logs, "purpose"),
        }

        return result
    except Exception as exc:
        logger.exception("vms stats failed: {}", exc)
        return JSONResponse(
            {"status": "error", "reason": "stats_failed"}, status_code=500
        )
