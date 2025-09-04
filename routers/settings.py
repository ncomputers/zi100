"""Settings management routes."""

from __future__ import annotations

import json
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from loguru import logger
from starlette.datastructures import FormData

from config import config
from core.config import (
    ANOMALY_ITEMS,
    COUNT_GROUPS,
    PPE_ITEMS,
    load_branding,
    save_branding,
    save_config,
)
from core.tracker_manager import reset_counts, save_cameras, start_tracker, stop_tracker
from modules.email_utils import send_email
from modules.utils import require_admin, require_roles
from schemas.alerts import EmailConfig

router = APIRouter(dependencies=[Depends(require_admin)])
BASE_DIR = Path(__file__).resolve().parent.parent
LOGO_DIR = BASE_DIR / "static" / "logos"
URL_RE = re.compile(r"^https?://")
templates_dir = str(BASE_DIR / "templates")


# init_context routine
def init_context(
    config: dict,
    trackers: Dict[int, "PersonTracker"],
    cameras: List[dict],
    redis_client,
    templates_path: str,
    config_path: str,
    branding_file: str,
):
    """Store shared objects for settings routes."""
    global cfg, trackers_map, cams, redis, templates, cfg_path, branding, branding_path, templates_dir
    cfg = config
    trackers_map = trackers
    cams = cameras
    redis = redis_client
    templates_dir = templates_path
    templates = Jinja2Templates(directory=templates_path)
    cfg_path = config_path
    branding_path = branding_file
    branding = load_branding(branding_file)


@router.get("/static/logos/{filename}")
async def serve_logo(filename: str):
    """Serve uploaded logos from a controlled directory."""
    file_path = LOGO_DIR / filename
    if not file_path.is_file():
        raise HTTPException(status_code=404)
    return FileResponse(file_path)


def set_cfg(new_cfg: dict) -> None:
    """Replace the global configuration."""
    global cfg
    cfg = new_cfg


def set_branding(new_branding: dict) -> None:
    """Replace the global branding dictionary."""
    global branding
    branding = new_branding


def parse_basic_settings(data: dict) -> dict:
    """Return a new configuration with basic settings applied."""
    new_cfg = cfg.copy()
    for key in [
        "max_capacity",
        "warn_threshold",
        "fps",
        "capture_buffer_seconds",
        "frame_skip",
        "line_ratio",
        "v_thresh",
        "debounce",
        "retry_interval",
        "conf_thresh",
        "helmet_conf_thresh",
        "person_model",
        "ppe_model",
        "max_retry",
        "chart_update_freq",
        "profiling_interval",
        "stream_mode",
        "face_match_thresh",
        "face_count_conf",
        "face_count_similarity",
        "face_count_min_size",
    ]:
        if key in data:
            val = data[key]
            new_cfg[key] = type(cfg.get(key, val))(val)
    for key in [
        "detect_helmet_color",
        "show_lines",
        "show_ids",
        "show_track_lines",
        "show_counts",
        "show_face_boxes",
        "enable_live_charts",
        "debug_logs",
        "enable_face_recognition",
        "enable_face_counting",
        "enable_profiling",
        "enable_person_tracking",
        "email_enabled",
    ]:
        val = data.get(key)
        new_cfg[key] = (
            bool(val)
            if isinstance(val, bool)
            else str(val).lower() in {"true", "on", "1"}
        )
    if data.get("track_ppe"):
        new_cfg["track_ppe"] = data["track_ppe"]
    if data.get("alert_anomalies"):
        new_cfg["alert_anomalies"] = data["alert_anomalies"]
    if data.get("preview_anomalies"):
        new_cfg["preview_anomalies"] = data["preview_anomalies"]
    if data.get("track_objects"):
        new_cfg["track_objects"] = data["track_objects"]
    return new_cfg


def parse_email_settings(form: FormData) -> EmailConfig:
    """Extract and validate email settings from a form."""
    data = dict(form)
    email_data: dict = {}
    for key in ["smtp_host", "smtp_user", "from_addr"]:
        val = data.get(key)
        if val:
            email_data[key] = val.strip()
    if data.get("smtp_port"):
        try:
            email_data["smtp_port"] = int(data["smtp_port"])
        except ValueError as exc:  # pragma: no cover - handled by caller
            raise ValueError("invalid_smtp_port") from exc
    if "use_tls" in data:
        email_data["use_tls"] = str(data["use_tls"]).lower() in {"true", "on", "1"}
    if "use_ssl" in data:
        email_data["use_ssl"] = str(data["use_ssl"]).lower() in {"true", "on", "1"}
    if data.get("smtp_pass"):
        email_data["smtp_pass"] = data["smtp_pass"]
    if email_data:
        validated = EmailConfig.model_validate(email_data)
        return validated
    return EmailConfig()


@router.get("/settings")
async def settings_page(request: Request):
    # Pull the latest config snapshot each request so tests modifying the global
    # config dictionary see the change in rendered templates.
    from jinja2 import TemplateNotFound

    from config import config as current_cfg

    global templates
    try:
        env = templates
        return env.TemplateResponse(
            "settings.html",
            {
                "request": request,
                "cfg": current_cfg,
                "now_ts": int(datetime.utcnow().timestamp()),
                "ppe_items": PPE_ITEMS,
                "alert_items": ANOMALY_ITEMS,
                "preview_items": ANOMALY_ITEMS,
                "count_options": list(COUNT_GROUPS.keys()),
            },
        )
    except TemplateNotFound:
        # Some tests initialise the settings router with a temporary template
        # directory that lacks ``settings.html``.  Recreate the templates
        # environment using the original ``templates_dir`` so subsequent
        # requests can still render the built-in templates.
        templates = Jinja2Templates(directory=templates_dir)
        return templates.TemplateResponse(
            "settings.html",
            {
                "request": request,
                "cfg": current_cfg,
                "now_ts": int(datetime.utcnow().timestamp()),
                "ppe_items": PPE_ITEMS,
                "alert_items": ANOMALY_ITEMS,
                "preview_items": ANOMALY_ITEMS,
                "count_options": list(COUNT_GROUPS.keys()),
            },
        )


@router.post("/settings")
async def update_settings(request: Request):
    global cfg, branding
    form = await request.form()
    data = dict(form)
    data.update(
        {
            "track_ppe": form.getlist("track_ppe"),
            "alert_anomalies": form.getlist("alert_anomalies"),
            "preview_anomalies": form.getlist("preview_anomalies"),
            "track_objects": form.getlist("track_objects"),
        }
    )
    if data.get("password") != cfg.get("settings_password"):
        return {"saved": False, "error": "auth"}
    raw_email_enabled = data.get("email_enabled")
    force_email = str(data.pop("force_email_enable", "")).lower() in {"true", "on", "1"}
    if raw_email_enabled and not cfg.get("email", {}).get("last_test_ts"):
        if not force_email:
            return {"saved": False, "error": "email_test_required"}
        logger.warning("email enabled without successful test")
    prev_tracking = cfg.get("enable_person_tracking", True)
    try:
        new_cfg = parse_basic_settings(data)
        email_cfg_obj = parse_email_settings(form)
    except ValueError as exc:
        return {"saved": False, "error": str(exc)}
    email_updates = email_cfg_obj.model_dump(exclude_none=True)
    new_cfg.setdefault("email", {}).update(email_updates)
    branding_updates = branding.copy()
    branding_updates["company_name"] = data.get(
        "company_name", branding_updates.get("company_name", "")
    )
    branding_updates["site_name"] = data.get(
        "site_name", branding_updates.get("site_name", "")
    )
    branding_updates["website"] = data.get(
        "website", branding_updates.get("website", "")
    )
    branding_updates["address"] = data.get(
        "address", branding_updates.get("address", "")
    )
    branding_updates["phone"] = data.get("phone", branding_updates.get("phone", ""))
    branding_updates["tagline"] = data.get(
        "tagline", branding_updates.get("tagline", "")
    )
    branding_updates["print_layout"] = data.get(
        "print_layout", branding_updates.get("print_layout", "A5")
    )
    if new_cfg.get("ffmpeg_supports_drop"):
        branding_updates["watermark"] = str(data.get("watermark", "off")).lower() in {
            "on",
            "true",
            "1",
        }
    else:
        branding_updates["watermark"] = False
    logo = form.get("logo")
    if logo and getattr(logo, "filename", ""):
        LOGO_DIR.mkdir(parents=True, exist_ok=True)
        for old in LOGO_DIR.glob("company_logo.*"):
            old.unlink(missing_ok=True)
        ext = Path(logo.filename).suffix or ".png"
        path = LOGO_DIR / f"company_logo{ext}"
        with path.open("wb") as f:
            f.write(await logo.read())
        branding_updates["company_logo"] = path.name
        branding_updates["company_logo_url"] = (
            f"/static/logos/{path.name}?v={int(time.time())}"
        )
    elif data.get("company_logo_url_input"):
        url = data["company_logo_url_input"].strip()
        if URL_RE.match(url):
            branding_updates["company_logo_url"] = url
            branding_updates["company_logo"] = ""
    footer_logo = form.get("footer_logo")
    if footer_logo and getattr(footer_logo, "filename", ""):
        LOGO_DIR.mkdir(parents=True, exist_ok=True)
        for old in LOGO_DIR.glob("footer_logo.*"):
            old.unlink(missing_ok=True)
        ext = Path(footer_logo.filename).suffix or ".png"
        path = LOGO_DIR / f"footer_logo{ext}"
        with path.open("wb") as f:
            f.write(await footer_logo.read())
        branding_updates["footer_logo"] = path.name
        branding_updates["footer_logo_url"] = (
            f"/static/logos/{path.name}?v={int(time.time())}"
        )
    elif data.get("footer_logo_url_input"):
        url = data["footer_logo_url_input"].strip()
        if URL_RE.match(url):
            branding_updates["footer_logo_url"] = url
            branding_updates["footer_logo"] = ""
    save_branding(branding_updates, branding_path)
    new_cfg["branding"] = branding_updates
    license_feats = new_cfg.get("license_info", {}).get("features", {})
    user_feats = new_cfg.get("features", {})
    new_cfg["features"] = {
        k: bool(user_feats.get(k)) and bool(license_feats.get(k)) for k in user_feats
    }
    set_branding(branding_updates)
    set_cfg(new_cfg)
    save_config(cfg, cfg_path, redis)
    from config import set_config as set_global_config

    set_global_config(cfg)
    for tr in trackers_map.values():
        tr.update_cfg(cfg)
    if prev_tracking != cfg.get("enable_person_tracking", True):
        if cfg.get("enable_person_tracking", True):
            for cam in cams:
                if cam.get("enabled", True):
                    start_tracker(cam, cfg, trackers_map, redis)
        else:
            for cid in list(trackers_map.keys()):
                stop_tracker(cid, trackers_map)
    from modules.profiler import start_profiler

    start_profiler(cfg)
    return {
        "saved": True,
        "logo_url": branding_updates.get("company_logo_url"),
        "footer_logo_url": branding_updates.get("footer_logo_url"),
    }


@router.post("/settings/email/test")
async def settings_email_test(request: Request):
    global cfg
    data = await request.json()
    recipient = data.get("recipient")
    if not recipient:
        return {"sent": False, "error": "missing_recipient"}
    payload_cfg = {
        k: data.get(k)
        for k in [
            "smtp_host",
            "smtp_port",
            "smtp_user",
            "smtp_pass",
            "use_tls",
            "use_ssl",
            "from_addr",
        ]
        if k in data
    }
    merged_cfg = {**cfg.get("email", {}), **payload_cfg}
    email_cfg = EmailConfig.model_validate(merged_cfg).model_dump(exclude_none=True)
    if not email_cfg.get("smtp_host"):
        return {"sent": False, "error": "missing_smtp_host"}
    try:
        success, err, response, msg_id = send_email(
            "Test Email",
            "This is a test email from Crowd Manager",
            [recipient],
            cfg=email_cfg,
        )
    except Exception:  # pragma: no cover - handled gracefully
        logger.exception("Test email send failed")
        cfg.setdefault("email", {})["last_test_ts"] = 0
        save_config(cfg, cfg_path, redis)
        return {"sent": False, "error": "exception"}
    if not success:
        return {"sent": False, "error": err}
    return {"sent": True}


@router.post("/settings/branding")
async def branding_update(
    request: Request,
    company_name: str = Form(""),
    logo: UploadFile | None = File(None),
):
    """Handle branding logo uploads with basic validation."""
    if logo is None:
        raise HTTPException(status_code=400, detail="logo required")
    if logo.content_type not in {"image/png", "image/jpeg", "image/jpg"}:
        raise HTTPException(status_code=400, detail="invalid file")
    data = await logo.read()
    if len(data) > 1_000_000:
        raise HTTPException(status_code=400, detail="file too large")
    return {"saved": True, "company_name": company_name}


@router.get("/settings/export")
async def export_settings(request: Request):
    """Download configuration and cameras as a single JSON payload."""
    from fastapi.responses import JSONResponse

    data = {"config": cfg, "cameras": cams}
    return JSONResponse(data)


@router.post("/settings/import")
async def import_settings(request: Request):
    """Import configuration and optional camera list."""
    data = await request.json()
    new_cfg = data.get("config", data)
    cams_data = data.get("cameras")
    cfg.update(new_cfg)
    save_config(cfg, cfg_path, redis)
    from config import set_config

    set_config(cfg)
    for tr in trackers_map.values():
        tr.update_cfg(cfg)
    from modules.profiler import start_profiler

    start_profiler(cfg)
    if isinstance(cams_data, list):
        # stop existing trackers
        for cid in list(trackers_map.keys()):
            stop_tracker(cid, trackers_map)
        cams[:] = cams_data
        save_cameras(cams, redis)
        for cam in cams:
            if cam.get("enabled", True):
                start_tracker(cam, cfg, trackers_map, redis)
    return {"saved": True}


@router.post("/reset")
async def reset_endpoint():
    reset_counts(trackers_map)
    return {"reset": True}


@router.get("/license")
async def license_page(request: Request):
    """Render a page for entering a license key."""
    return templates.TemplateResponse("license.html", {"request": request, "cfg": cfg})


@router.post("/license")
async def activate_license(request: Request):
    data = await request.json()
    key = data.get("key")
    from modules.license import verify_license

    info = verify_license(key)
    if not info.get("valid"):
        return {"error": info.get("error")}
    cfg["license_key"] = key
    cfg["license_info"] = info
    cfg["features"] = info.get("features", cfg.get("features", {}))
    save_config(cfg, cfg_path, redis)
    redis.set("license_info", json.dumps(info))
    from config import set_config

    set_config(cfg)
    return {"activated": True, "info": info}
