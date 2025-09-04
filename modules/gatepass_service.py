"""Helpers for gatepass token generation and notifications."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Optional

import redis
from fastapi import Request
from jinja2 import Environment, FileSystemLoader, select_autoescape
from loguru import logger

from config import config as cfg
from utils.image import decode_base64_image
from utils.redis import trim_sorted_set_sync

_redis: Optional[redis.Redis] = None


# init routine
def init(redis_client: redis.Redis) -> None:
    """Initialize redis client for gatepass helpers."""
    global _redis
    _redis = redis_client


# build_qr_link routine
def build_qr_link(gate_id: str, request: Request) -> str:
    """Return absolute URL to view gate pass for QR code generation."""
    base = str(request.base_url).rstrip("/")
    return f"{base}/gatepass/view/{gate_id}" if gate_id else f"{base}/gatepass/view/"


# Jinja environment for offline template rendering
_template_dir = Path(__file__).resolve().parent.parent / "templates"
_env = Environment(
    loader=FileSystemLoader(_template_dir),
    autoescape=select_autoescape(["html", "xml"]),
)
_env.globals["url_for"] = lambda name, path: (
    f"/static/{path}" if name == "static" else path
)


# render_gatepass_card routine
def render_gatepass_card(rec: dict, qr_image: str | None = None) -> str:
    """Return HTML for gate pass card using shared template."""
    rec_local = dict(rec)
    if rec_local.get("signature") and rec_local["signature"].startswith("static/"):
        rec_local["signature"] = f"/{rec_local['signature']}"
    branding = cfg.get("branding", {})
    cfg_local = dict(cfg)
    cfg_local["branding"] = dict(branding)
    logo = cfg_local["branding"].get("company_logo_url") or cfg_local.get("logo_url")
    if logo and logo.startswith("static/"):
        cfg_local["branding"]["company_logo_url"] = f"/{logo}"
        logo = cfg_local["branding"]["company_logo_url"]
    if logo and not (logo.startswith("http") or logo.startswith("/static/")):
        cfg_local["branding"]["company_logo_url"] = ""
        cfg_local["logo_url"] = ""
    footer = cfg_local["branding"].get("footer_logo_url") or cfg_local.get("logo2_url")
    if footer and footer.startswith("static/"):
        cfg_local["branding"]["footer_logo_url"] = f"/{footer}"
    color_map = {
        "pending": "warning text-dark",
        "approved": "success",
        "rejected": "danger",
        "created": "secondary",
    }
    status_color = color_map.get(rec.get("status", "created"), "secondary")
    template = _env.get_template("partials/gatepass_card.html")
    return template.render(
        rec=rec_local,
        branding=cfg_local.get("branding", {}),
        cfg=cfg_local,
        status_color=status_color,
        qr_img=qr_image,
        signature_url=rec_local.get("signature"),
    )


def _find_gatepass(gate_id: str) -> tuple[dict, str | bytes] | None:
    """Return gate pass record and raw entry from redis."""
    if not _redis:
        raise ValueError("Redis not initialized")
    try:
        data = _redis.hget("gatepass:active", gate_id)
    except Exception as exc:
        logger.exception("failed to fetch gate pass {}: {}", gate_id, exc)
        raise RuntimeError("failed to fetch gate passes") from exc
    if data:
        obj = json.loads(data if isinstance(data, str) else data.decode())
        return obj, data
    return None


# update_status routine
def update_status(gate_id: str, status: str) -> bool:
    """Update status of a gate pass and persist to redis."""
    res = _find_gatepass(gate_id)
    if not res:
        return False
    obj, entry = res
    obj["status"] = status
    _redis.zrem("vms_logs", entry)
    _redis.zadd("vms_logs", {json.dumps(obj): obj["ts"]})
    trim_sorted_set_sync(_redis, "vms_logs", obj["ts"])
    try:
        if status == "rejected" or obj.get("valid_to", 0) < int(time.time()):
            _redis.hdel("gatepass:active", gate_id)
            if obj.get("phone"):
                _redis.hdel("gatepass:active_phone", obj["phone"])
        else:
            _redis.hset("gatepass:active", gate_id, json.dumps(obj))
            if obj.get("phone"):
                _redis.hset("gatepass:active_phone", obj["phone"], gate_id)
    except Exception:
        logger.exception("Failed to update gate pass index for {}", gate_id)
    return True


# save_signature routine
def save_signature(gate_id: str, data: str) -> str:
    """Save base64 signature image and update record."""
    if not _redis:
        raise ValueError("Redis not initialized")
    if not data:
        return ""
    sig_dir = Path("static/signatures")
    sig_dir.mkdir(parents=True, exist_ok=True)
    path = sig_dir / f"{gate_id}.png"
    try:
        img_bytes = decode_base64_image(data)
        path.write_bytes(img_bytes)
    except ValueError:
        return ""
    res = _find_gatepass(gate_id)
    stored_path = f"/static/signatures/{gate_id}.png"
    if res:
        obj, entry = res
        obj["signature"] = stored_path
        _redis.zrem("vms_logs", entry)
        _redis.zadd("vms_logs", {json.dumps(obj): obj["ts"]})
        trim_sorted_set_sync(_redis, "vms_logs", obj["ts"])
    return stored_path
