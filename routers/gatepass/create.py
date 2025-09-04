from __future__ import annotations

"""Gatepass creation and management routes."""

import base64
import json
import time
from datetime import datetime
from typing import Optional

import cv2
import numpy as np
from fastapi import APIRouter, BackgroundTasks, Body, File, Form, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse
from loguru import logger

import routers.visitor as visitor
from config import config as cfg
from modules import export, face_db, gatepass_service, visitor_db
from modules.email_utils import sign_token
from routers.visitor_utils import visitor_disabled_response
from schemas.gatepass import GatepassBase
from utils.face_db_utils import add_face_to_known_db, save_base64_to_image
from utils.ids import generate_id
from utils.image import decode_base64_image
from utils.redis import trim_sorted_set_async as trim_sorted_set

from . import (
    _cache_gatepass,
    _get_gatepass,
    _load_gatepass,
    _qr_data_uri,
    _sanitize_placeholders,
    _save_gatepass,
    config_obj,
    redis,
    templates,
)

router = APIRouter()


def _send_pdf_email(
    entry: dict, email: str, request: Request, digital_pass_url: str
) -> None:
    """Generate gate pass PDF and send via email."""

    from . import send_email

    gate_id = entry.get("gate_id")
    body = f"Welcome! Your gate pass is ready: {digital_pass_url}"
    qr_link = gatepass_service.build_qr_link(gate_id, request)
    qr_img = _qr_data_uri(qr_link)
    _sanitize_placeholders(entry)

    card_fields = [
        "gate_id",
        "name",
        "phone",
        "email",
        "host",
        "purpose",
        "visitor_type",
        "company_name",
        "time",
        "valid_to",
        "status",
        "image",
        "signature",
    ]
    card = {key: entry.get(key) for key in card_fields}

    branding = cfg.get("branding", {})
    org = branding.get("company_name")
    site = branding.get("site_name")

    html = templates.get_template("gatepass_print.html").render(
        request=request,
        card=card,
        cfg=cfg,
        org=org,
        site=site,
        mode="pdf",
        qr_img=qr_img,
    )

    pdf_bytes = None
    try:
        result = export.export_pdf(html, f"gatepass_{gate_id}")
        if isinstance(result, dict):
            logger.error("PDF export failed for {}: {}", gate_id, result.get("error"))
        elif result is None:
            logger.error("PDF export returned None for {}", gate_id)
        else:
            pdf_path = export.EXPORT_DIR / f"gatepass_{gate_id}.pdf"
            try:
                pdf_bytes = pdf_path.read_bytes()
            except Exception:
                pdf_bytes = b""
    except Exception:
        logger.exception("Failed to export PDF for gate pass {}", gate_id)
    if pdf_bytes:
        send_email(
            "Welcome",
            body,
            [email],
            config_obj.get("email", {}),
            attachment=pdf_bytes,
            attachment_name=f"gatepass_{gate_id}.pdf",
            attachment_type="application/pdf",
        )
    else:
        send_email("Welcome", body, [email], config_obj.get("email", {}))


async def _extract_photo(photo: UploadFile | None, captured: str) -> bytes:
    """Return raw image bytes from captured data or uploaded file."""
    img_bytes = b""
    if captured:
        try:
            img_bytes = decode_base64_image(captured)
        except ValueError:
            img_bytes = b""
    if not img_bytes and photo:
        img_bytes = await photo.read()
    return img_bytes


def _merge_invite_fields(data: dict, invite_id: str) -> dict:
    """Populate missing form fields from invite data."""
    if not invite_id:
        return data
    try:
        raw = redis.hgetall(f"invite:{invite_id}")
        invite_data = {
            (k.decode() if isinstance(k, bytes) else k): (
                v.decode() if isinstance(v, bytes) else v
            )
            for k, v in raw.items()
        }
    except Exception:
        invite_data = {}
    if not invite_data:
        return data
    merged = data.copy()
    merged["name"] = merged.get("name") or invite_data.get("name", merged.get("name"))
    merged["phone"] = merged.get("phone") or invite_data.get(
        "phone", merged.get("phone")
    )
    merged["email"] = merged.get("email") or invite_data.get(
        "email", merged.get("email")
    )
    merged["host"] = merged.get("host") or invite_data.get("host", merged.get("host"))
    merged["purpose"] = merged.get("purpose") or invite_data.get(
        "purpose", merged.get("purpose")
    )
    merged["visitor_type"] = merged.get("visitor_type") or invite_data.get(
        "visitor_type", merged.get("visitor_type")
    )
    merged["company_name"] = merged.get("company_name") or invite_data.get(
        "company", merged.get("company_name")
    )
    if not merged.get("valid_to"):
        merged["valid_to"] = (
            invite_data.get("expiry") or invite_data.get("visit_time") or ""
        )
    return merged


def _validate_active_pass(redis, phone: str) -> None:
    """Raise if an active gate pass already exists for the phone."""
    ts_int = int(time.time())
    try:
        existing_id = redis.hget("gatepass:active_phone", phone)
    except Exception as exc:
        raise RuntimeError("redis_unavailable") from exc
    if not existing_id:
        return
    if isinstance(existing_id, bytes):
        existing_id = existing_id.decode()
    try:
        raw = redis.hget("gatepass:active", existing_id)
    except Exception as exc:
        raise RuntimeError("redis_unavailable") from exc
    if raw:
        obj = json.loads(raw if isinstance(raw, str) else raw.decode())
        if obj.get("status") != "rejected" and obj.get("valid_to", ts_int) > ts_int:
            raise ValueError("active_exists")
    try:
        redis.hdel("gatepass:active", existing_id)
        redis.hdel("gatepass:active_phone", phone)
    except Exception:
        logger.exception("Failed to clean stale gate pass {}", existing_id)


@router.post("/gatepass/auto_crop")
async def gatepass_auto_crop(image: UploadFile = File(...)) -> JSONResponse:
    """Return cropped face from uploaded image using face model."""
    img_bytes = await image.read()
    if face_db.face_app is None:
        return JSONResponse({"error": "model"}, status_code=500)
    arr = cv2.imdecode(np.frombuffer(img_bytes, np.uint8), cv2.IMREAD_COLOR)
    if arr is None:
        return JSONResponse({"error": "decode"}, status_code=400)
    rgb = cv2.cvtColor(arr, cv2.COLOR_BGR2RGB)
    faces = face_db.face_app.get(rgb)
    if not faces:
        return JSONResponse({"error": "no_face"})
    x1, y1, x2, y2 = [int(v) for v in faces[0].bbox]
    crop = rgb[y1:y2, x1:x2]
    _, buf = cv2.imencode(".jpg", cv2.cvtColor(crop, cv2.COLOR_RGB2BGR))
    b64 = base64.b64encode(buf.tobytes()).decode()
    return JSONResponse({"image": b64})


@router.get("/gatepass/active")
async def gatepass_active(phone: str) -> JSONResponse:
    """Check if an active gate pass exists for phone."""
    now_ts = int(time.time())
    try:
        gate_id = redis.hget("gatepass:active_phone", phone)
    except Exception:
        logger.exception(
            "Redis unavailable while checking active gate pass for {}",
            phone,
        )
        return JSONResponse({"error": "redis_unavailable"}, status_code=503)
    if gate_id:
        if isinstance(gate_id, bytes):
            gate_id = gate_id.decode()
        try:
            raw = redis.hget("gatepass:active", gate_id)
        except Exception:
            logger.exception("Redis unavailable while fetching gate pass {}", gate_id)
            return JSONResponse({"error": "redis_unavailable"}, status_code=503)
        if raw:
            obj = json.loads(raw if isinstance(raw, str) else raw.decode())
            if obj.get("status") != "rejected" and obj.get("valid_to", now_ts) > now_ts:
                return JSONResponse({"active": True, "gate_id": gate_id})
        try:
            redis.hdel("gatepass:active", gate_id)
            redis.hdel("gatepass:active_phone", phone)
        except Exception:
            logger.exception("Failed to clean inactive gate pass {}", gate_id)
    return JSONResponse({"active": False})


@router.post("/gatepass/create")
async def gatepass_create(
    request: Request,
    name: str = Form(...),
    phone: str = Form(...),
    email: str = Form(""),
    host: str = Form(...),
    purpose: str = Form(...),
    visitor_type: str = Form(...),
    host_department: str = Form(""),
    company_name: str = Form(""),
    id_proof_type: str = Form(""),
    photo: Optional[UploadFile] = File(None),
    captured: str = Form(""),
    no_photo: str = Form("off"),
    invite_id: str = Form(""),
    valid_to: str = Form(""),
    needs_approval: str = Form("off"),
    approver_email: str = Form(""),
    background_tasks: BackgroundTasks = BackgroundTasks(),
) -> JSONResponse:
    """Create a new gate pass entry."""
    if not config_obj.get("features", {}).get("visitor_mgmt"):
        return visitor_disabled_response()

    # Import here so tests can monkeypatch ``gatepass.send_email`` and have the
    # change reflected inside this function.
    from . import send_email

    if redis is None:
        return JSONResponse({"error": "redis_unavailable"}, status_code=503)
    try:
        redis.ping()
    except Exception:
        logger.exception("Redis unavailable during gate pass creation")
        return JSONResponse({"error": "redis_unavailable"}, status_code=503)

    # FastAPI's Form defaults appear as Form(...) when called directly in tests
    if not isinstance(id_proof_type, str):
        id_proof_type = ""
    if not isinstance(invite_id, str):
        invite_id = ""
    if not isinstance(valid_to, str):
        valid_to = ""
    if not isinstance(approver_email, str):
        approver_email = ""
    if not isinstance(host_department, str):
        host_department = ""
    if not isinstance(company_name, str):
        company_name = ""
    if not isinstance(email, str):
        email = ""

    if needs_approval == "on" and not approver_email:
        return JSONResponse({"error": "approver_required"}, status_code=400)

    img_bytes = b""
    if no_photo != "on":
        img_bytes = await _extract_photo(photo, captured)
    b64 = base64.b64encode(img_bytes).decode() if img_bytes else ""
    ts = time.time()
    gate_id = f"GP{generate_id()[:8].upper()}"
    ts_int = int(ts)

    data = {
        "name": name,
        "phone": phone,
        "email": email,
        "host": host,
        "purpose": purpose,
        "visitor_type": visitor_type,
        "company_name": company_name,
        "valid_to": valid_to,
    }
    data = _merge_invite_fields(data, invite_id)
    name = data["name"]
    phone = data["phone"]
    email = data["email"]
    host = data["host"]
    purpose = data["purpose"]
    visitor_type = data["visitor_type"]
    company_name = data["company_name"]
    valid_to = data["valid_to"]

    # reject past validity
    if valid_to:
        valid_ts = int(datetime.fromisoformat(valid_to.replace(" ", "T")).timestamp())
        if valid_ts < ts_int:
            return JSONResponse({"error": "invalid_date"}, status_code=400)
    else:
        valid_ts = ts_int
    try:
        _validate_active_pass(redis, phone)
    except RuntimeError:
        return JSONResponse({"error": "redis_unavailable"}, status_code=503)
    except ValueError:
        return JSONResponse({"error": "active_exists"}, status_code=400)

    status = "approved"
    if needs_approval == "on":
        status = "pending"
    base = config_obj.get("base_url", "").rstrip("/")
    if not base:
        base = str(request.base_url).rstrip("/")
    digital_pass_url = f"{base}/gatepass/view/{gate_id}"
    qr_content = digital_pass_url
    qr_img = _qr_data_uri(qr_content)
    entry = {
        "gate_id": gate_id,
        "ts": ts_int,
        "name": name,
        "phone": phone,
        "email": email,
        "host": host,
        "host_department": host_department,
        "purpose": purpose,
        "visitor_type": visitor_type,
        "company_name": company_name,
        "id_proof_type": id_proof_type,
        "status": status,
        "valid_from": ts_int,
        "valid_to": valid_ts,
        "approver_email": approver_email,
        "qr": qr_content,
        "invite_id": invite_id,
    }
    if img_bytes:
        entry["image"] = b64
    elif no_photo == "on":
        entry["no_photo"] = True

    try:
        _save_gatepass(entry)
    except Exception:
        logger.exception("Redis unavailable while saving gate pass {}", gate_id)
        return JSONResponse({"error": "redis_unavailable"}, status_code=503)
    image_url = ""
    if img_bytes:
        image_path = save_base64_to_image(b64, filename_prefix="gp", subdir="known")
        image_url = f"{image_path}?v={ts_int}"
        add_face_to_known_db(
            image_path=image_path,
            name=name,
            phone=phone,
            visitor_type=visitor_type,
            gate_pass_id=entry["gate_id"],
            metadata={
                "source": "gatepass",
                "host": host,
                "timestamp": datetime.now().isoformat(),
            },
        )
        try:
            face_db.insert(img_bytes, entry["gate_id"], source="gatepass")
        except Exception:
            pass
    else:
        image_path = None
    try:
        visitor_db.init_db(redis)
    except Exception:
        logger.exception(
            "Redis unavailable while initializing visitor DB for {}",
            gate_id,
        )
        return JSONResponse({"error": "redis_unavailable"}, status_code=503)
    try:
        vid = visitor._save_visitor_master(
            name,
            email,
            phone,
            visitor_type=visitor_type,
            company_name=company_name,
            photo_url=image_url,
        )
    except Exception:
        logger.exception("Failed to save visitor record for {}", gate_id)
        return JSONResponse({"error": "visitor_save_failed"}, status_code=500)
    entry["visitor_id"] = vid
    if host:
        visitor_db.save_host(host, dept=host_department)
        try:
            import json as _js

            redis.hset("host_master", host, _js.dumps({"email": ""}))
            visitor.invalidate_host_cache()
        except Exception:
            logger.exception("Failed to cache host info for {}", host)
    approval_url = None
    if needs_approval == "on" and approver_email:
        tok = f"{entry['gate_id']}:{sign_token(entry['gate_id'], config_obj.get('secret_key', 'secret'))}"
        approve_url = str(
            request.url_for("gatepass_approve").include_query_params(token=tok)
        )
        reject_url = str(
            request.url_for("gatepass_reject").include_query_params(token=tok)
        )
        approval_url = approve_url
        photo_html = ""
        if img_bytes:
            photo_html = f"<p><img src='data:image/jpeg;base64,{base64.b64encode(img_bytes).decode()}' width='120'></p>"
        msg = (
            f"<h3>Gate Pass Approval Required</h3>"
            f"<p>Name: {name}<br>Company: {company_name}<br>Host: {host}<br>Purpose: {purpose}<br>"
            f"Date: {datetime.fromtimestamp(ts).strftime('%Y-%m-%d %H:%M')}</p>"
            f"{photo_html}"
            f"<p><a href='{approve_url}'>Approve</a> | "
            f"<a href='{reject_url}'>Reject</a></p>"
        )
        send_email(
            "Gate Pass Approval",
            msg,
            [approver_email],
            config_obj.get("email", {}),
            html=True,
        )
    elif email and email.strip():
        background_tasks.add_task(
            _send_pdf_email,
            entry.copy(),
            email,
            request,
            digital_pass_url,
        )

    resp = {
        "saved": True,
        "gate_id": entry["gate_id"],
        "time": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(ts)),
        "status": status,
        "qr": qr_content,
        "qr_img": qr_img,
        "digital_pass_url": digital_pass_url,
    }
    if approval_url:
        resp["approval_url"] = approval_url
    return JSONResponse(resp)


@router.get("/gatepass/verify/{gate_id}")
async def gatepass_verify_form(gate_id: str, request: Request):
    """Display gate pass details and prompt for host confirmation."""
    if not config_obj.get("features", {}).get("visitor_mgmt"):
        return HTMLResponse("disabled", status_code=403)
    try:
        item = _get_gatepass(gate_id)
    except RuntimeError:
        return HTMLResponse("redis_unavailable", status_code=503)
    if not item:
        return HTMLResponse("not found", status_code=404)
    item["time"] = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(item["ts"]))
    if item.get("valid_from"):
        item["valid_from_str"] = time.strftime(
            "%Y-%m-%d %H:%M:%S", time.localtime(item["valid_from"])
        )
    if item.get("valid_to"):
        item["valid_to_str"] = time.strftime(
            "%Y-%m-%d %H:%M:%S", time.localtime(item["valid_to"])
        )
    branding = cfg.get("branding", {})
    return templates.TemplateResponse(
        "host_verify.html",
        {"request": request, "rec": item, "cfg": cfg, "branding": branding},
    )


@router.post("/gatepass/verify/{gate_id}")
async def gatepass_verify(gate_id: str, request: Request, host_pass: str = Form(...)):
    """Confirm host for the given gate pass."""
    if not config_obj.get("features", {}).get("visitor_mgmt"):
        return HTMLResponse("disabled", status_code=403)
    try:
        item = _get_gatepass(gate_id)
    except RuntimeError:
        return HTMLResponse("redis_unavailable", status_code=503)
    if not item:
        return HTMLResponse("not found", status_code=404)
    if item.get("host", "").strip().lower() != host_pass.strip().lower():
        return HTMLResponse("host mismatch", status_code=403)
    new_status = (
        "Meeting in progress"
        if item.get("status") != "Meeting in progress"
        else "Completed"
    )
    item["status"] = new_status
    try:
        redis.hset(f"gatepass:pass:{gate_id}", mapping={"status": new_status})
        redis.zadd("vms_logs", {json.dumps(item): item["ts"]})
        await trim_sorted_set(redis, "vms_logs", item["ts"])
    except Exception:
        logger.exception("Redis unavailable while verifying gate pass {}", gate_id)
        return HTMLResponse("redis_unavailable", status_code=503)
    branding = cfg.get("branding", {})
    return templates.TemplateResponse(
        "gatepass_verify.html",
        {
            "request": request,
            "rec": item,
            "cfg": cfg,
            "branding": branding,
            "status_color": "success",
        },
    )


@router.post("/gatepass/sign/{gate_id}")
async def gatepass_sign(gate_id: str, payload: dict = Body(...)):
    """Persist visitor signature for the given gate pass."""
    if not config_obj.get("features", {}).get("visitor_mgmt"):
        return visitor_disabled_response()
    image_data = payload.get("image", "")
    path = gatepass_service.save_signature(gate_id, image_data)
    if path:
        try:
            redis.hset(f"gatepass:pass:{gate_id}", "signature", path)
        except Exception:
            logger.exception(
                "Redis unavailable while saving signature for {}",
                gate_id,
            )
            return JSONResponse({"error": "redis_unavailable"}, status_code=503)
    return JSONResponse({"saved": bool(path), "path": path})


@router.post("/gatepass/checkout/{gate_id}")
async def gatepass_checkout(
    gate_id: str, request: Request, host_pass: str | None = None
):
    """Record visitor exit and update pass status."""
    if not config_obj.get("features", {}).get("visitor_mgmt"):
        return visitor_disabled_response()
    if host_pass is None:
        host_pass = request.query_params.get("host_pass")
    if host_pass is None:
        try:
            data = await request.json()
            host_pass = data.get("host_pass")
        except Exception:
            host_pass = None
    try:
        item = _get_gatepass(gate_id)
    except RuntimeError:
        return JSONResponse({"error": "redis_unavailable"}, status_code=503)
    if not item:
        return JSONResponse({"error": "not_found"}, status_code=404)
    if item.get("host", "").strip().lower() != (host_pass or "").strip().lower():
        return JSONResponse({"error": "verification_failed"}, status_code=403)
    now = int(time.time())
    status = "Completed" if now <= int(item.get("valid_to", now)) else "Expired"
    item["status"] = status
    item["exit_ts"] = now
    try:
        redis.hset(
            f"gatepass:pass:{gate_id}", mapping={"status": status, "exit_ts": now}
        )
        entries = redis.zrange("vms_logs", 0, -1)
        for e in entries:
            rec = json.loads(e if isinstance(e, str) else e.decode())
            if rec.get("gate_id") == gate_id:
                redis.zrem("vms_logs", e)
                break
        redis.zadd("vms_logs", {json.dumps(item): item["ts"]})
        await trim_sorted_set(redis, "vms_logs", item["ts"])
    except Exception:
        logger.exception("Redis unavailable while checking out gate pass {}", gate_id)
        return JSONResponse({"error": "redis_unavailable"}, status_code=503)
    return JSONResponse({"status": status})


@router.get("/gatepass/{gate_id}", response_model=GatepassBase)
async def gatepass_get(gate_id: str) -> GatepassBase | JSONResponse:
    """Return single gate pass record."""
    try:
        obj = _load_gatepass(gate_id)
    except RuntimeError:
        return JSONResponse({"error": "redis_unavailable"}, status_code=503)
    if obj:
        return GatepassBase(**obj)
    return JSONResponse({"error": "not_found"}, status_code=404)


@router.put("/gatepass/update/{gate_id}")
async def gatepass_update(gate_id: str, request: Request) -> JSONResponse:
    """Update an existing gate pass."""
    data = await request.form()
    try:
        obj = _load_gatepass(gate_id)
    except RuntimeError:
        return JSONResponse({"error": "redis_unavailable"}, status_code=503)
    if obj:
        obj.update(data)
        try:
            entries = redis.zrange("vms_logs", 0, -1)
            for e in entries:
                rec = json.loads(e if isinstance(e, str) else e.decode())
                if rec.get("gate_id") == gate_id:
                    redis.zrem("vms_logs", e)
                    break
            redis.zadd("vms_logs", {json.dumps(obj): int(obj["ts"])})
            await trim_sorted_set(redis, "vms_logs", int(obj["ts"]))
            _cache_gatepass(obj)
        except Exception:
            logger.exception(
                "Redis unavailable while updating gate pass {}",
                gate_id,
            )
            return JSONResponse({"error": "redis_unavailable"}, status_code=503)
        return JSONResponse({"updated": True})

    return JSONResponse({"error": "not_found"}, status_code=404)


@router.delete("/gatepass/delete/{gate_id}")
async def gatepass_delete(gate_id: str) -> JSONResponse:
    """Delete a gate pass entry."""
    try:
        entries = redis.zrevrange("vms_logs", 0, -1)
    except Exception:
        logger.exception("Redis unavailable while deleting gate pass {}", gate_id)
        return JSONResponse({"error": "redis_unavailable"}, status_code=503)
    for e in entries:
        obj = json.loads(e)
        if obj.get("gate_id") == gate_id:
            try:
                redis.zrem("vms_logs", e)
                redis.delete(
                    f"gatepass:pass:{gate_id}",
                    f"gatepass:signature:{gate_id}",
                    f"gatepass:cache:{gate_id}",
                )
            except Exception:
                logger.exception(
                    "Redis unavailable while deleting gate pass {}",
                    gate_id,
                )
                return JSONResponse({"error": "redis_unavailable"}, status_code=503)
            return JSONResponse({"deleted": True})
    logger.warning(f"Gate pass not found: {gate_id}")
    return JSONResponse({"error": "not_found"}, status_code=404)
