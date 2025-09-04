from __future__ import annotations

"""Gatepass router package with shared helpers and combined routes."""

import base64
import io
import json
import time
from typing import Optional

import qrcode
from fastapi import APIRouter
from fastapi.templating import Jinja2Templates
from loguru import logger
from pydantic import ValidationError

from config import config as cfg
from modules import gatepass_service, visitor_db
from modules.email_utils import send_email, sign_token
from routers import visitor
from schemas.gatepass import GatepassRequiredFields
from utils.face_db_utils import add_face_to_known_db, save_base64_to_image
from utils.redis import trim_sorted_set_sync

router = APIRouter()

# cache configuration
GATEPASS_CACHE_TTL = 24 * 60 * 60  # 24 hours
GATEPASS_RETENTION_SECS = visitor.VISITOR_LOG_RETENTION_SECS

# placeholders for context-initialized objects
config_obj: dict = {}
redis = None
templates: Jinja2Templates | None = None
face_db = None


def _qr_data_uri(data: str) -> str:
    """Return a data URI for the given QR data."""
    buf = io.BytesIO()
    qrcode.make(data).save(buf, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


def parse_timestamp(value) -> int | None:
    """Safely convert a Redis field to an integer timestamp."""
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _normalize_gatepass(rec: dict) -> dict:
    """Ensure timestamp fields on a gate pass are integers.

    Unknown or non-numeric values are removed from ``rec``.  The dictionary
    is modified in-place and also returned for convenience.
    """

    for field in ("ts", "valid_from", "valid_to"):
        parsed = parse_timestamp(rec.get(field))
        if parsed is not None:
            rec[field] = parsed
        else:
            rec.pop(field, None)
    return rec


def _cache_gatepass(entry: dict) -> None:
    """Store gate pass data in Redis using standard keys."""
    entry = _normalize_gatepass(entry)
    gate_id = entry.get("gate_id")
    if not gate_id:
        return
    gate_key = f"gatepass:pass:{gate_id}"
    sign_key = f"gatepass:signature:{gate_id}"
    cache_key = f"gatepass:cache:{gate_id}"
    try:
        redis.hset(gate_key, mapping=entry)
        redis.expire(gate_key, GATEPASS_RETENTION_SECS)
        sig = sign_token(gate_id, config_obj.get("secret_key", "secret"))
        redis.set(sign_key, sig, ex=GATEPASS_RETENTION_SECS)
        redis.set(cache_key, json.dumps(entry), ex=GATEPASS_CACHE_TTL)
    except Exception:
        logger.exception("Failed to cache gate pass {}", gate_id)


def _fetch_cached_gatepass(gate_id: str) -> dict | None:
    """Return gate pass from JSON cache if available."""
    cache_key = f"gatepass:cache:{gate_id}"
    try:
        data = redis.get(cache_key)
    except Exception:
        logger.exception("Redis unavailable while loading gate pass {}", gate_id)
        raise RuntimeError("redis_unavailable")
    if not data:
        return None
    try:
        return _normalize_gatepass(json.loads(data))
    except Exception:
        try:
            redis.delete(cache_key)
        except Exception:
            logger.exception("Redis cleanup failed for gate pass {}", gate_id)
        return None


def _fetch_hashed_gatepass(gate_id: str) -> dict | None:
    """Return gate pass from Redis hash and update JSON cache."""
    try:
        data = redis.hgetall(f"gatepass:pass:{gate_id}")
    except Exception:
        logger.exception("Redis unavailable while loading gate pass {}", gate_id)
        raise RuntimeError("redis_unavailable")
    if not data:
        return None
    item = {
        (k.decode() if isinstance(k, bytes) else k): (
            v.decode() if isinstance(v, bytes) else v
        )
        for k, v in data.items()
    }
    item = _normalize_gatepass(item)
    try:
        redis.set(f"gatepass:cache:{gate_id}", json.dumps(item), ex=GATEPASS_CACHE_TTL)
    except Exception:
        logger.exception("Redis cache set failed for gate pass {}", gate_id)
    return item


def _scan_logs_for_gatepass(gate_id: str) -> dict | None:
    """Search the log stream for a gate pass and cache it if found."""
    try:
        entries = redis.zrevrange("vms_logs", 0, -1)
    except Exception:
        logger.exception(
            "Redis unavailable while scanning logs for gate pass {}",
            gate_id,
        )
        raise RuntimeError("redis_unavailable")
    for e in entries:
        obj = json.loads(e)
        if obj.get("gate_id") == gate_id:
            obj = _normalize_gatepass(obj)
            _cache_gatepass(obj)
            return obj
    return None


def _load_gatepass(gate_id: str) -> Optional[dict]:
    """Retrieve gate pass data from cache, hash or logs."""
    return (
        _fetch_cached_gatepass(gate_id)
        or _fetch_hashed_gatepass(gate_id)
        or _scan_logs_for_gatepass(gate_id)
    )


def _sanitize_placeholders(rec: dict) -> None:
    """Replace placeholder strings with empty values."""
    placeholders = {".", "work"}
    for key, value in list(rec.items()):
        if isinstance(value, str) and value.strip().lower() in placeholders:
            rec[key] = ""


def validate_gatepass_entry(entry: dict) -> list[str]:
    """Return list of missing required fields for gate pass entry."""
    try:
        GatepassRequiredFields(**entry)
        return []
    except ValidationError as exc:
        return [str(err.get("loc", [])[0]) for err in exc.errors()]


def _save_gatepass(entry: dict) -> None:
    entry = _normalize_gatepass(entry)
    try:
        existing = redis.zrange("vms_logs", 0, -1)
        for e in existing:
            obj = json.loads(e if isinstance(e, str) else e.decode())
            if obj.get("gate_id") == entry.get("gate_id"):
                redis.zrem("vms_logs", e)
                break
        redis.zadd("vms_logs", {json.dumps(entry): entry["ts"]})
        trim_sorted_set_sync(redis, "vms_logs", entry["ts"])
        _cache_gatepass(entry)
        try:
            redis.hset("gatepass:active", entry["gate_id"], json.dumps(entry))
            phone = entry.get("phone")
            if phone:
                redis.hset("gatepass:active_phone", phone, entry["gate_id"])
        except Exception:
            logger.exception("Failed to index gate pass {}", entry.get("gate_id"))
        invite_id = entry.get("invite_id")
        if invite_id:
            try:
                redis.hset("gatepass:by_invite", invite_id, entry["gate_id"])
            except Exception:
                logger.exception("Failed to index gate pass by invite {}", invite_id)
        phone = entry.get("phone")
        if phone:
            key = f"visits:phone:{phone}"
            try:
                data = redis.get(key)
                count = 0
                if data:
                    try:
                        obj = json.loads(data)
                        count = int(obj.get("count", 0))
                    except Exception:
                        count = int(data or 0)
                count += 1
                value = json.dumps({"count": count, "last_id": entry.get("gate_id")})
                redis.set(key, value, ex=visitor.VISITOR_LOG_RETENTION_SECS)
            except Exception:
                logger.exception("Failed to update visit count for {}", phone)
    except Exception:
        logger.exception("Failed to save gate pass {}", entry.get("gate_id"))


def _get_gatepass(gate_id: str) -> dict | None:
    """Return gate pass using cache with fallback to Redis hash."""
    cache_key = f"gatepass:cache:{gate_id}"
    try:
        cached = redis.get(cache_key)
        if cached:
            return json.loads(cached)
    except Exception:
        logger.exception(
            "Redis unavailable while retrieving cached gate pass {}",
            gate_id,
        )
        raise RuntimeError("redis_unavailable")
    try:
        raw = redis.hgetall(f"gatepass:pass:{gate_id}")
    except Exception:
        logger.exception("Redis unavailable while retrieving gate pass {}", gate_id)
        raise RuntimeError("redis_unavailable")
    if raw:
        item = {
            (k.decode() if isinstance(k, bytes) else k): (
                v.decode() if isinstance(v, bytes) else v
            )
            for k, v in raw.items()
        }
        try:
            redis.setex(cache_key, GATEPASS_CACHE_TTL, json.dumps(item))
        except Exception:
            logger.exception("Failed to cache gate pass {}", gate_id)
        return item
    return None


def _format_gatepass_times(entry: dict) -> dict:
    """Populate formatted time fields on a gate pass record.

    Ensures that ``ts``, ``valid_from`` and ``valid_to`` values are numeric
    before formatting them into human readable strings.  The ``entry`` dict is
    modified in-place and returned for convenience.
    """

    def _to_int(value):
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    ts = _to_int(entry.get("ts"))
    if ts is not None:
        entry["time"] = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(ts))

    valid_from = _to_int(entry.get("valid_from"))
    if valid_from is not None:
        entry["valid_from_str"] = time.strftime(
            "%Y-%m-%d %H:%M:%S", time.localtime(valid_from)
        )

    valid_to = _to_int(entry.get("valid_to"))
    if valid_to is not None:
        entry["valid_to_str"] = time.strftime(
            "%Y-%m-%d %H:%M:%S", time.localtime(valid_to)
        )

    return entry


def init_context(cfg_obj: dict, redis_client, templates_path: str) -> None:
    """Initialize shared context for gatepass submodules.

    The gatepass package exposes a few module-level objects (``config_obj``,
    ``redis`` and ``templates``) that other submodules import directly. Simply
    reassigning these globals would leave stale references inside those
    submodules.  Instead we mutate ``config_obj`` in place and manually update
    the attributes of the already imported modules so that every caller sees
    the new objects.
    """

    global redis, templates

    # mutate the shared config dict instead of reassigning so imported aliases
    # continue to reference the updated values
    config_obj.clear()
    config_obj.update(cfg_obj)

    # update shared state
    redis = redis_client
    templates = Jinja2Templates(directory=templates_path)
    visitor.get_context().redis = redis_client
    gatepass_service.init(redis_client)

    # propagate updated objects to submodules that imported them directly
    create.config_obj = config_obj
    create.redis = redis
    create.templates = templates
    approval.config_obj = config_obj
    approval.redis = redis
    approval.templates = templates
    reports.config_obj = config_obj
    reports.redis = redis
    reports.templates = templates
    try:  # pragma: no cover - exercised in tests via init_context
        from weasyprint import HTML

        HTML(string="<p>test</p>").write_pdf(io.BytesIO())
    except Exception as exc:  # pragma: no cover
        # WeasyPrint is used for PDF generation in certain gatepass flows.
        # Missing the dependency should not prevent the rest of the
        # application from working, so log a warning instead of aborting
        # initialization. PDF export routes will surface errors if invoked.
        logger.warning("weasyprint unavailable: {}", exc)


from . import approval, create, reports  # noqa: E402
from .approval import (  # noqa: E402,F401
    gatepass_approve,
    gatepass_cancel,
    gatepass_reject,
    gatepass_resend,
    pending_requests,
)
from .create import (  # noqa: E402,F401
    gatepass_active,
    gatepass_auto_crop,
    gatepass_checkout,
    gatepass_create,
    gatepass_delete,
    gatepass_get,
    gatepass_sign,
    gatepass_update,
    gatepass_verify,
    gatepass_verify_form,
)
from .reports import (  # noqa: E402,F401
    gatepass_card,
    gatepass_export,
    gatepass_list,
    gatepass_print,
    gatepass_view,
)

router.include_router(reports.router)
router.include_router(create.router)
router.include_router(approval.router)

# expose commonly used helpers
__all__ = [
    "router",
    "init_context",
    "gatepass_service",
    "templates",
    "_save_gatepass",
    "validate_gatepass_entry",
    "gatepass_print",
    "gatepass_card",
    "gatepass_view",
    "gatepass_list",
    "gatepass_export",
    "gatepass_auto_crop",
    "gatepass_active",
    "gatepass_create",
    "gatepass_verify_form",
    "gatepass_verify",
    "gatepass_sign",
    "gatepass_checkout",
    "gatepass_get",
    "gatepass_update",
    "gatepass_delete",
    "gatepass_approve",
    "gatepass_reject",
    "pending_requests",
    "gatepass_resend",
    "gatepass_cancel",
    "send_email",
]
