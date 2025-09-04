"""Visitor invite routes."""

from __future__ import annotations

import base64
import binascii
import json
import re
import time
import uuid
from datetime import datetime
from types import SimpleNamespace
from typing import List

from fastapi import APIRouter, BackgroundTasks, Depends, Form, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from loguru import logger

from config import config
from modules import visitor_db
from modules.email_utils import send_email
from modules.utils import require_viewer
from utils.ids import generate_id
from utils.image import decode_base64_image
from utils.redis import trim_sorted_set_async as trim_sorted_set

from ..visitor_utils import require_visitor_mgmt, visitor_disabled_response
from . import (
    _save_host_master,
    _save_visitor_master,
    get_context,
    get_host_names_cached,
)

router = APIRouter()


async def _trim(client, key, ts):
    await trim_sorted_set(client, key, ts)


def _build_invite_link(
    request: Request, invite_id: str, ctx: SimpleNamespace | None = None
) -> str:
    """Return a fully qualified link to the public invite form.

    ``ctx`` is optional so the helper can be called directly in tests or
    scripts without relying on FastAPI's dependency injection.
    """
    if ctx is None:
        from . import get_context as _get_context

        ctx = _get_context()
    from . import config_obj as _cfg

    base_url = (
        ctx.config.get("base_url") or _cfg.get("base_url") or config.get("base_url", "")
    ).rstrip("/")
    if not base_url:
        proto = request.headers.get("x-forwarded-proto", request.url.scheme)
        base_url = f"{proto}://{request.url.netloc}"
    return f"{base_url}/invite/form?id={invite_id}"


def _validate_invite_form(form: dict) -> dict:
    """Validate invite creation form and return error messages."""
    errors: dict[str, str] = {}
    if not form.get("name", "").strip():
        errors["name"] = "Name is required"
    if not form.get("phone", "").strip():
        errors["phone"] = "Phone is required"
    if not form.get("visitor_type", "").strip():
        errors["visitor_type"] = "Visitor type is required"
    if not form.get("company", "").strip():
        errors["company"] = "Company is required"
    if not form.get("host", "").strip():
        errors["host"] = "Host is required"
    if not form.get("visit_time", "").strip():
        errors["visit_time"] = "Visit time is required"
    if not form.get("purpose", "").strip():
        errors["purpose"] = "Purpose is required"
    if not form.get("photo", "").strip() and form.get("no_photo") != "on":
        errors["photo"] = "Photo is required"
    return errors


async def _persist_invite(redis, record: dict) -> None:
    """Persist invite record and indexes to Redis."""
    redis.zadd("invite_records", {json.dumps(record, sort_keys=True): record["ts"]})
    await _trim(redis, "invite_records", record["ts"])
    redis.zadd("invite_ids", {record["id"]: record["ts"]})
    await _trim(redis, "invite_ids", record["ts"])
    redis.hset(f"invite:{record['id']}", mapping=record)


def _generate_gatepass(obj: dict, iid: str, request: Request | None = None):
    """Create a gate pass entry from invite data."""
    from routers import gatepass

    from . import Path

    existing = gatepass.redis.hget("gatepass:by_invite", iid) if gatepass.redis else None
    gate_id = (
        existing.decode() if isinstance(existing, bytes) else existing
        if existing
        else f"GP{generate_id()[:8].upper()}"
    )
    photo_b64 = ""
    photo_url = obj.get("photo_url", "")
    if photo_url:
        try:
            path = Path("public") / photo_url.lstrip("/")
            photo_b64 = base64.b64encode(path.read_bytes()).decode()
        except Exception:
            logger.exception("failed to read invite photo {}", photo_url)
    ts = int(time.time())
    valid_to_str = obj.get("expiry") or obj.get("visit_time") or ""
    try:
        valid_ts = (
            int(datetime.fromisoformat(valid_to_str.replace(" ", "T")).timestamp())
            if valid_to_str
            else ts + 24 * 60 * 60
        )
    except Exception:
        valid_ts = ts + 24 * 60 * 60
    qr = ""
    try:
        qr = gatepass.gatepass_service.build_qr_link(gate_id, request)
    except Exception:
        qr = ""
    entry = {
        "gate_id": gate_id,
        "ts": ts,
        "name": obj.get("name", ""),
        "phone": obj.get("phone", ""),
        "email": obj.get("email", ""),
        "host": obj.get("host", ""),
        "purpose": obj.get("purpose", ""),
        "visitor_type": obj.get("visitor_type", ""),
        "company_name": obj.get("company", ""),
        "gov_id": obj.get("gov_id", ""),
        "vehicle": obj.get("vehicle", ""),
        "status": "approved",
        "image": photo_b64,
        "valid_from": ts,
        "valid_to": valid_ts,
        "qr": qr,
        "invite_id": iid,
        "photo_source": obj.get("photo_source", "none"),
    }
    gatepass._save_gatepass(entry)
    return gate_id


@router.get("/invite")
async def invite_panel(
    request: Request,
    user: dict | RedirectResponse = Depends(require_viewer),
    ctx: SimpleNamespace = Depends(require_visitor_mgmt),
):
    """Display the invite management panel."""

    if not isinstance(user, (dict, RedirectResponse)):
        user = require_viewer(request)
    if not isinstance(ctx, SimpleNamespace):
        ctx = get_context()
    if isinstance(user, RedirectResponse):
        return user
    return ctx.templates.TemplateResponse(
        "invite_panel.html",
        {"request": request, "cfg": config, "host_names": get_host_names_cached()},
    )


@router.post("/invite/create")
async def invite_create(
    request: Request,
    background_tasks: BackgroundTasks = None,
    name: str = Form(""),
    phone: str = Form(""),
    email: str = Form(""),
    visitor_type: str = Form(""),
    company: str = Form(""),
    host: str = Form(""),
    visit_time: str = Form(""),
    expiry: str = Form(""),
    purpose: str = Form(""),
    photo: str = Form(""),
    send_mail: str = Form("off"),
    no_photo: str = Form("off"),
    link: str | None = None,
    ctx: SimpleNamespace = Depends(get_context),
):
    from . import Path

    background_tasks = background_tasks or BackgroundTasks()
    if not isinstance(ctx, SimpleNamespace):
        ctx = get_context()
    if not ctx.config.get("features", {}).get("visitor_mgmt"):
        return visitor_disabled_response()
    today = datetime.now().strftime("%Y%m%d")

    rand = str(uuid.uuid4().int)[:4]
    invite_id = f"VST-{today}-{rand}"
    link_url = _build_invite_link(request, invite_id, ctx)
    base = link_url.split("/invite/form")[0]
    if request.query_params.get("link"):
        errors: dict[str, str] = {}
        if not host.strip():
            errors["host"] = "Host is required"
        if errors:
            return JSONResponse({"errors": errors}, status_code=400)
        rec = {
            "id": invite_id,
            "host": host,
            "status": "link",
            "invite_source": "link",
            "ts": int(time.time()),
        }
        if expiry:
            rec["expiry"] = expiry
        if purpose:
            rec["purpose"] = purpose
        await _persist_invite(ctx.redis, rec)
        return {"link": link_url}

    form = {
        "name": name,
        "phone": phone,
        "email": email,
        "visitor_type": visitor_type,
        "company": company,
        "host": host,
        "visit_time": visit_time,
        "purpose": purpose,
        "photo": photo,
        "no_photo": no_photo,
    }
    errors = _validate_invite_form(form)
    if errors:
        return JSONResponse({"errors": errors}, status_code=400)

    img_bytes = None
    photo_url = ""
    if photo:
        if not photo.startswith("data:image/jpeg;base64,"):
            return JSONResponse({"error": "invalid_photo"}, status_code=400)
        try:
            img_bytes = decode_base64_image(photo)
        except ValueError:
            return JSONResponse({"error": "invalid_photo"}, status_code=400)
        max_bytes = int(ctx.config.get("invite_photo_max_bytes", 200000))
        if len(img_bytes) > max_bytes:
            return JSONResponse({"error": "photo_too_large"}, status_code=400)
        out_dir = Path("public") / "invite_photos"
        out_dir.mkdir(parents=True, exist_ok=True)
        photo_path = out_dir / f"{invite_id}.jpg"
        with open(photo_path, "wb") as f:
            f.write(img_bytes)
        photo_url = f"/invite_photos/{invite_id}.jpg"

    rec = {
        "id": invite_id,
        "name": name,
        "phone": phone,
        "email": email,
        "visitor_type": visitor_type,
        "company": company,
        "host": host,
        "visit_time": visit_time,
        "expiry": expiry,
        "purpose": purpose,
        "photo_url": photo_url,
        "status": "created",
        "invite_source": "manual",
        "ts": int(time.time()),
    }
    await _persist_invite(ctx.redis, rec)

    _save_visitor_master(name, email, phone, visitor_type, company, photo_url)
    req = {
        "id": invite_id,
        "name": name,
        "phone": phone,
        "visitor_type": visitor_type,
        "company": company,
        "host": host,
        "status": "pending",
        "ts": rec["ts"],
    }
    ctx.redis.zadd("visit_requests", {json.dumps(req): req["ts"]})
    await _trim(ctx.redis, "visit_requests", req["ts"])
    if img_bytes:
        try:
            from modules import face_db

            face_db.add_face_if_single_detected(img_bytes, invite_id)
        except Exception:
            pass
    # notify host for approval
    try:
        host_info = visitor_db.get_host(host or "") or {}
        host_email = host_info.get("email", "") if isinstance(host_info, dict) else ""
    except Exception:
        host_email = ""
    if host:
        _save_host_master(host, host_email)
    if host_email:
        approve_url = f"{base}/invite/approve/{invite_id}"
        reject_url = f"{base}/invite/reject/{invite_id}"
        body = ctx.templates.get_template("email_invite.html").render(
            name=name, host=host, approve_url=approve_url, reject_url=reject_url
        )
        background_tasks.add_task(
            send_email,
            "Visit Invite Approval",
            body,
            [host_email],
            ctx.config.get("email", {}),
            True,
        )
    if send_mail == "on" and email:
        msg = f"Your visit to {host} at {visit_time} is scheduled."
        background_tasks.add_task(
            send_email,
            "Visit Invite",
            msg,
            [email],
            ctx.config.get("email", {}),
        )
    return {"saved": True, "id": invite_id, "link": link_url}


@router.get("/invite/cctv")
async def invite_cctv(ctx: SimpleNamespace = Depends(get_context)):
    """Return configured CCTV cameras for invite capture."""
    return [
        {"id": c.get("id"), "name": c.get("name")}
        for c in ctx.cam_list or []
        if c.get("type") != "local"
    ]


@router.get("/invite/list")
async def invite_list(
    request: Request,
    cursor: int = 0,
    limit: int = 20,
    status: List[str] | None = Query(None),
    invite_source: List[str] | None = Query(None),
    days: int = Query(30),
    ctx: SimpleNamespace = Depends(get_context),
):
    """Return paginated invite records with optional status filters."""
    if not ctx.config.get("features", {}).get("visitor_mgmt"):
        return visitor_disabled_response()
    end = cursor + limit - 1
    ids = ctx.redis.zrevrange("invite_ids", cursor, end)
    fields = [
        "id",
        "name",
        "phone",
        "email",
        "visitor_type",
        "company",
        "host",
        "visit_time",
        "status",
        "invite_source",
        "ts",
    ]
    rows = []
    for iid in ids:
        iid = iid.decode() if isinstance(iid, bytes) else iid
        vals = ctx.redis.hmget(f"invite:{iid}", fields)
        rec = {
            k: (v.decode() if isinstance(v, bytes) else v)
            for k, v in zip(fields, vals)
            if v
        }
        if status and rec.get("status") not in status:
            continue
        if invite_source and rec.get("invite_source") not in invite_source:
            continue
        if "ts" in rec:
            try:
                rec["ts"] = int(rec["ts"])
            except (TypeError, ValueError):
                pass
            if days and rec["ts"] < int(time.time()) - days * 86400:
                continue
        rows.append(rec)
    next_cursor = cursor + len(ids) if len(ids) == limit else None
    if not request.query_params:
        return rows
    return {"invites": rows, "next_cursor": next_cursor}


@router.get("/invite/lookup")
async def invite_lookup(phone: str, ctx: SimpleNamespace = Depends(get_context)):
    """Lookup visitor info by phone number."""
    info = visitor_db.get_visitor_by_phone(phone)
    if not info:
        return {}
    entries = [json.loads(e) for e in ctx.redis.zrevrange("vms_logs", 0, -1)]
    visits = [e for e in entries if e.get("phone") == phone]
    info["visits"] = len(visits)
    info["last_id"] = visits[0].get("visitor_id") if visits else info.get("id")
    return info


@router.get("/invite/form")
async def invite_public_form(
    id: str, request: Request, ctx: SimpleNamespace = Depends(get_context)
):
    if not ctx.config.get("features", {}).get("visitor_mgmt"):
        return RedirectResponse("/", status_code=302)
    rec_raw = ctx.redis.hgetall(f"invite:{id}")
    if not rec_raw:
        return HTMLResponse("invalid", status_code=404)
    rec = {
        k.decode() if isinstance(k, bytes) else k: (
            v.decode() if isinstance(v, bytes) else v
        )
        for k, v in rec_raw.items()
    }
    return ctx.templates.TemplateResponse(
        "invite_public.html",
        {
            "request": request,
            "cfg": config,
            "invite_id": id,
            "invite": rec,
            "host_names": get_host_names_cached(),
        },
    )


@router.get("/invite/thanks")
async def invite_thanks(
    request: Request,
    visitor_id: str | None = None,
    ctx: SimpleNamespace = Depends(get_context),
):
    if not isinstance(ctx, SimpleNamespace):
        ctx = get_context()
    if not ctx.config.get("features", {}).get("visitor_mgmt"):
        return RedirectResponse("/", status_code=302)
    return ctx.templates.TemplateResponse(
        "thank_you.html",
        {"request": request, "cfg": config, "visitor_id": visitor_id},
    )


@router.get("/invite/complete/{iid}")
async def invite_complete_form(
    iid: str, request: Request, ctx: SimpleNamespace = Depends(get_context)
):
    if not isinstance(ctx, SimpleNamespace):
        ctx = get_context()
    if not ctx.config.get("features", {}).get("visitor_mgmt"):
        return RedirectResponse("/", status_code=302)
    rec_raw = ctx.redis.hgetall(f"invite:{iid}")
    if not rec_raw:
        return HTMLResponse("invalid", status_code=404)
    rec = {
        k.decode() if isinstance(k, bytes) else k: (
            v.decode() if isinstance(v, bytes) else v
        )
        for k, v in rec_raw.items()
    }
    return ctx.templates.TemplateResponse(
        "invite_complete.html",
        {"request": request, "cfg": config, "invite_id": iid, "invite": rec},
    )


@router.post("/invite/complete/{iid}")
async def invite_complete_submit(
    iid: str,
    government_id: str = Form(""),
    phone: str = Form(""),
    purpose: str = Form(""),
    vehicle: str = Form(""),
    photo: str = Form(""),
    ctx: SimpleNamespace = Depends(get_context),
):
    if not isinstance(ctx, SimpleNamespace):
        ctx = get_context()
    from . import Path

    if not ctx.config.get("features", {}).get("visitor_mgmt"):
        return JSONResponse({"errors": {"form": "disabled"}}, status_code=403)
    rec_raw = ctx.redis.hgetall(f"invite:{iid}")
    if not rec_raw:
        return JSONResponse({"errors": {"id": "invalid"}}, status_code=404)
    rec = {
        (k.decode() if isinstance(k, bytes) else k): (
            v.decode() if isinstance(v, bytes) else v
        )
        for k, v in rec_raw.items()
    }
    errors = {}
    if not government_id.strip():
        errors["government_id"] = "Government ID is required"
    if not (phone.strip() or rec.get("phone")):
        errors["phone"] = "Contact number is required"
    if not (purpose.strip() or rec.get("purpose")):
        errors["purpose"] = "Purpose is required"
    if not photo.strip() and not rec.get("photo_url", "").strip():
        errors["photo"] = "Photo is required"
    if errors:
        return JSONResponse({"errors": errors}, status_code=400)
    img_bytes = None
    photo_url = rec.get("photo_url", "")
    if photo:
        if not photo.startswith("data:image/jpeg;base64,"):
            return JSONResponse({"error": "invalid_photo"}, status_code=400)
        try:
            img_bytes = decode_base64_image(photo)
        except ValueError:
            return JSONResponse({"error": "invalid_photo"}, status_code=400)
        max_bytes = int(ctx.config.get("invite_photo_max_bytes", 200000))
        if len(img_bytes) > max_bytes:
            return JSONResponse({"error": "photo_too_large"}, status_code=400)
        out_dir = Path("public") / "invite_photos"
        out_dir.mkdir(parents=True, exist_ok=True)
        photo_path = out_dir / f"{iid}.jpg"
        with open(photo_path, "wb") as f:
            f.write(img_bytes)
        photo_url = f"/invite_photos/{iid}.jpg"
    rec.update(
        {
            "gov_id": government_id,
            "phone": phone or rec.get("phone", ""),
            "purpose": purpose or rec.get("purpose", ""),
            "vehicle": vehicle,
            "photo_url": photo_url,
        }
    )
    ctx.redis.hset(f"invite:{iid}", mapping=rec)
    try:
        gate_id = _generate_gatepass(rec, iid, None)
    except Exception:
        logger.exception("gatepass generation failed for {}", iid)
        return JSONResponse({"error": "gatepass_failed"}, status_code=500)
    return {"ok": True, "gate_id": gate_id}


@router.post("/invite/form/submit")
async def invite_public_submit(
    request: Request,
    id: str = Form(...),
    name: str = Form(""),
    phone: str = Form(""),
    email: str = Form(""),
    visitor_type: str = Form(""),
    company: str = Form(""),
    host: str = Form(""),
    visit_time: str = Form(""),
    purpose_text: str = Form(""),
    photo: str = Form(""),
    photo_source: str = Form("none"),
    photo_waived: str = Form("off"),
    photo_waiver_reason: str = Form(""),
    ctx: SimpleNamespace = Depends(get_context),
):
    if not isinstance(ctx, SimpleNamespace):
        ctx = get_context()
    from . import Path

    if not ctx.config.get("features", {}).get("visitor_mgmt"):
        return JSONResponse({"errors": {"form": "disabled"}}, status_code=403)
    rec_raw = ctx.redis.hgetall(f"invite:{id}")
    if not rec_raw:
        return JSONResponse({"errors": {"id": "invalid"}}, status_code=404)
    rec = {
        (k.decode() if isinstance(k, bytes) else k): (
            v.decode() if isinstance(v, bytes) else v
        )
        for k, v in rec_raw.items()
    }

    errors = {}
    if not name.strip():
        errors["name"] = "Name is required"
    if not phone.strip():
        errors["phone"] = "Phone is required"
    if email and not re.match(r"^[^\s@]+@[^\s@]+\.[^\s@]+$", email):
        errors["email"] = "Invalid email address"
    if not visitor_type.strip():
        errors["visitor_type"] = "Visitor type is required"
    if not company.strip():
        errors["company"] = "Company is required"
    if not host.strip():
        errors["host"] = "Host is required"
    if not visit_time.strip():
        errors["visit_time"] = "Visit time is required"
    purpose_text = purpose_text.strip()
    if not purpose_text:
        errors["purpose_text"] = "Purpose is required"
    elif not 3 <= len(purpose_text) <= 120:
        errors["purpose_text"] = "Purpose must be between 3 and 120 characters"
    valid_sources = {"upload", "camera", "none"}
    if photo_source not in valid_sources:
        errors["photo_source"] = "invalid"
    if photo_source in {"upload", "camera"} and not photo.strip() and not rec.get("photo_url", "").strip():
        errors["photo"] = "Photo is required"
    if photo_source == "none" and photo_waived != "on" and not rec.get("photo_url", "").strip():
        errors["photo"] = "Photo is required"
    if errors:
        return JSONResponse({"errors": errors}, status_code=400)

    img_bytes = None
    photo_url = ""
    if photo:
        if not photo.startswith("data:image/jpeg;base64,"):
            return JSONResponse({"errors": {"photo": "invalid"}}, status_code=400)
        try:
            img_bytes = decode_base64_image(photo)
        except ValueError:
            return JSONResponse({"errors": {"photo": "invalid"}}, status_code=400)
        max_bytes = int(ctx.config.get("invite_photo_max_bytes", 200000))
        if len(img_bytes) > max_bytes:
            return JSONResponse({"errors": {"photo": "too_large"}}, status_code=400)
        out_dir = Path("public") / "invite_photos"
        out_dir.mkdir(parents=True, exist_ok=True)
        photo_path = out_dir / f"{id}.jpg"
        with open(photo_path, "wb") as f:
            f.write(img_bytes)
        photo_url = f"/invite_photos/{id}.jpg"

    prev_status = rec.get("status")
    update_data = {
        "name": name,
        "phone": phone,
        "email": email,
        "visitor_type": visitor_type,
        "company": company,
        "host": host or rec.get("host", ""),
        "visit_time": visit_time,
        "purpose": "Other",
        "purpose_text": purpose_text,
        "status": "pending",
        "invite_source": "link",
        "photo_source": photo_source,
    }
    if photo_waived == "on":
        update_data["photo_waived"] = "1"
        if photo_waiver_reason.strip():
            update_data["photo_waiver_reason"] = photo_waiver_reason.strip()
    if photo_url:
        update_data["photo_url"] = photo_url
    rec.update(update_data)
    visitor_id = _save_visitor_master(
        name, email, phone, visitor_type, company, photo_url
    )
    rec["visitor_id"] = visitor_id
    if rec.get("host"):
        try:
            _save_host_master(rec.get("host", ""))
        except Exception:
            pass
    ctx.redis.hset(f"invite:{id}", mapping=rec)
    ts = int(rec["ts"])
    ctx.redis.zadd("invite_records", {json.dumps(rec, sort_keys=True): ts})
    await _trim(ctx.redis, "invite_records", ts)
    entries = ctx.redis.zrevrange("visit_requests", 0, -1)
    updated = False
    for e in entries:
        obj = json.loads(e)
        if obj.get("id") == id:
            update_obj = {
                "name": name,
                "phone": phone,
                "status": "pending",
                "visit_time": visit_time,
                "purpose": "Other",
                "purpose_text": purpose_text,
                "visitor_type": visitor_type,
                "company": company,
                "host": rec.get("host", ""),
            }
            if photo_waived == "on":
                update_obj["photo_waived"] = "1"
                if photo_waiver_reason.strip():
                    update_obj["photo_waiver_reason"] = photo_waiver_reason.strip()
            if photo_url:
                update_obj["photo_url"] = photo_url
            obj.update(update_obj)
            ctx.redis.zrem("visit_requests", e)
            ctx.redis.zadd("visit_requests", {json.dumps(obj): obj["ts"]})
            await _trim(ctx.redis, "visit_requests", int(obj["ts"]))
            updated = True
            break
    if not updated:
        req = {
            "id": id,
            "name": name,
            "phone": phone,
            "host": rec.get("host", ""),
            "visit_time": visit_time,
            "purpose": "Other",
            "purpose_text": purpose_text,
            "visitor_type": visitor_type,
            "company": company,
            "status": "pending",
            "ts": ts,
            "visitor_id": visitor_id,
        }
        if photo_waived == "on":
            req["photo_waived"] = "1"
            if photo_waiver_reason.strip():
                req["photo_waiver_reason"] = photo_waiver_reason.strip()
        if photo_url:
            req["photo_url"] = photo_url
        ctx.redis.zadd("visit_requests", {json.dumps(req): ts})
        await _trim(ctx.redis, "visit_requests", ts)
    if img_bytes:
        try:
            face_db.add_face_if_single_detected(img_bytes, id)
        except Exception:
            pass
    if prev_status == "accepted_pending_details":
        from routers import gatepass

        existing = ctx.redis.hget("gatepass:by_invite", id)
        gate_id = (
            existing.decode() if isinstance(existing, bytes) else existing
            if existing
            else f"GP{generate_id()[:8].upper()}"
        )
        photo_b64 = ""
        photo_url = rec.get("photo_url", "")
        if photo_url:
            try:
                path = Path("public") / photo_url.lstrip("/")
                photo_b64 = base64.b64encode(path.read_bytes()).decode()
            except Exception:
                logger.exception("failed to read invite photo {}", photo_url)
        valid_to_str = rec.get("expiry") or rec.get("visit_time") or ""
        try:
            valid_ts = (
                int(datetime.fromisoformat(valid_to_str.replace(" ", "T")).timestamp())
                if valid_to_str
                else ts + 24 * 60 * 60
            )
        except Exception:
            valid_ts = ts + 24 * 60 * 60
        qr = ""
        try:
            qr = gatepass.gatepass_service.build_qr_link(gate_id, request)
        except Exception:
            qr = ""
        entry = {
            "gate_id": gate_id,
            "ts": ts,
            "name": rec.get("name", ""),
            "phone": rec.get("phone", ""),
            "email": rec.get("email", ""),
            "host": rec.get("host", ""),
            "purpose": rec.get("purpose", ""),
            "visitor_type": rec.get("visitor_type", ""),
            "company_name": rec.get("company", ""),
            "status": "approved",
            "image": photo_b64,
            "valid_from": ts,
            "valid_to": valid_ts,
            "qr": qr,
            "invite_id": id,
            "photo_source": rec.get("photo_source", "none"),
        }
        try:
            gatepass._save_gatepass(entry)
        except Exception:
            logger.exception("gatepass generation failed for {}", id)
            return {"saved": True, "visitor_id": visitor_id, "error": "gatepass_failed"}
        rec["status"] = "approved"
        ctx.redis.hset(f"invite:{id}", mapping=rec)
        ctx.redis.zadd("invite_records", {json.dumps(rec, sort_keys=True): ts})
        await _trim(ctx.redis, "invite_records", ts)
        return {"saved": True, "visitor_id": visitor_id, "gate_id": gate_id}
    return {"saved": True, "visitor_id": visitor_id}


@router.get("/invite/{iid}")
async def invite_get(iid: str, ctx: SimpleNamespace = Depends(get_context)):
    """Return invite details for the given ID."""
    if not ctx.config.get("features", {}).get("visitor_mgmt"):
        return visitor_disabled_response()
    try:
        rec_raw = ctx.redis.hgetall(f"invite:{iid}")
    except Exception:
        return JSONResponse({"error": "redis_unavailable"}, status_code=503)
    if not rec_raw:
        return JSONResponse({"error": "not_found"}, status_code=404)
    rec = {
        (k.decode() if isinstance(k, bytes) else k): (
            v.decode() if isinstance(v, bytes) else v
        )
        for k, v in rec_raw.items()
    }
    return rec


@router.get("/invite/approve/{iid}")
@router.put("/invite/approve/{iid}")
async def invite_approve(
    iid: str, request: Request = None, ctx: SimpleNamespace = Depends(get_context)
):
    if not isinstance(ctx, SimpleNamespace):
        ctx = get_context()
    if not ctx.config.get("features", {}).get("visitor_mgmt"):
        return visitor_disabled_response()
    data = ctx.redis.hgetall(f"invite:{iid}")
    if not data:
        if request and request.method == "GET":
            return HTMLResponse("Invite not found", status_code=404)
        return {"error": "not_found"}
    obj = {
        k.decode() if isinstance(k, bytes) else k: (
            v.decode() if isinstance(v, bytes) else v
        )
        for k, v in data.items()
    }
    if not obj.get("id_proof_type"):
        return {"error": "missing_fields", "fields": ["id_proof_type"]}
    obj["status"] = "accepted_pending_details"
    ts = int(time.time())
    obj["ts"] = ts
    ctx.redis.hset(f"invite:{iid}", mapping=obj)
    ctx.redis.zadd("invite_records", {json.dumps(obj, sort_keys=True): ts})
    await _trim(ctx.redis, "invite_records", ts)
    details_url = f"/invite/form?id={iid}"
    if request and request.method == "GET":
        return RedirectResponse(details_url)
    return {"ok": True, "details_url": details_url}


@router.get("/invite/reject/{iid}")
@router.put("/invite/reject/{iid}")
async def invite_reject(
    iid: str, request: Request = None, ctx: SimpleNamespace = Depends(get_context)
):
    if not isinstance(ctx, SimpleNamespace):
        ctx = get_context()
    """Mark invite as rejected."""
    if not ctx.config.get("features", {}).get("visitor_mgmt"):
        return visitor_disabled_response()
    data = ctx.redis.hgetall(f"invite:{iid}")
    if not data:
        if request and request.method == "GET":
            return HTMLResponse("Invite not found", status_code=404)
        return {"error": "not_found"}
    obj = {
        k.decode() if isinstance(k, bytes) else k: (
            v.decode() if isinstance(v, bytes) else v
        )
        for k, v in data.items()
    }
    obj["status"] = "rejected"
    ts = int(obj.get("ts", 0))
    obj["ts"] = ts
    ctx.redis.hset(f"invite:{iid}", mapping=obj)
    ctx.redis.zadd("invite_records", {json.dumps(obj, sort_keys=True): ts})
    await _trim(ctx.redis, "invite_records", ts)
    if request and request.method == "GET":
        return HTMLResponse("Invite rejected")
    return {"ok": True}


@router.put("/invite/hold/{iid}")
async def invite_hold(iid: str, ctx: SimpleNamespace = Depends(get_context)):
    if not isinstance(ctx, SimpleNamespace):
        ctx = get_context()
    """Mark invite as on-hold."""
    if not ctx.config.get("features", {}).get("visitor_mgmt"):
        return visitor_disabled_response()
    data = ctx.redis.hgetall(f"invite:{iid}")
    if not data:
        return {"error": "not_found"}
    obj = {
        k.decode() if isinstance(k, bytes) else k: (
            v.decode() if isinstance(v, bytes) else v
        )
        for k, v in data.items()
    }
    obj["status"] = "hold"
    ts = int(obj.get("ts", 0))
    obj["ts"] = ts
    ctx.redis.hset(f"invite:{iid}", mapping=obj)
    ctx.redis.zadd("invite_records", {json.dumps(obj, sort_keys=True): ts})
    await _trim(ctx.redis, "invite_records", ts)
    return {"ok": True}


@router.delete("/invite/delete/{iid}")
async def invite_delete(iid: str, ctx: SimpleNamespace = Depends(get_context)):
    if not ctx.config.get("features", {}).get("visitor_mgmt"):
        return visitor_disabled_response()
    data = ctx.redis.hgetall(f"invite:{iid}")
    if not data:
        return {"error": "not_found"}
    obj = {
        k.decode() if isinstance(k, bytes) else k: (
            v.decode() if isinstance(v, bytes) else v
        )
        for k, v in data.items()
    }
    try:
        ts = int(obj.get("ts", 0))
        obj["ts"] = ts
        serialized = json.dumps(obj, sort_keys=True)
        ctx.redis.zrem("invite_records", serialized)
    except Exception:
        pass
    ctx.redis.zrem("invite_ids", iid)
    ctx.redis.delete(f"invite:{iid}")
    return {"ok": True}
