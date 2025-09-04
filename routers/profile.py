"""User profile management routes."""

from __future__ import annotations

import io
import os
import time
from pathlib import Path
from typing import Dict

from fastapi import APIRouter, Body, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from PIL import Image, ImageOps

from utils.ids import generate_id

router = APIRouter()

cfg: dict = {}
redis = None
templates: Jinja2Templates
BASE_DIR = Path(__file__).resolve().parent.parent
UPLOAD_DIR = BASE_DIR / "static" / "profile"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


def init_context(config: dict, redis_client, templates_path: str) -> None:
    """Store shared objects for profile routes."""
    global cfg, redis, templates
    cfg = config
    cfg.setdefault("preferences", {})
    redis = redis_client
    templates = Jinja2Templates(directory=templates_path)
    tz = cfg["preferences"].get("timezone")
    if tz:
        os.environ["TZ"] = tz
        try:
            time.tzset()
        except AttributeError:
            pass


async def _process_photo(photo: UploadFile) -> str:
    """Validate and store the uploaded profile photo."""
    if photo.content_type not in {"image/jpeg", "image/png"}:
        raise HTTPException(status_code=400, detail="invalid image type")
    content = await photo.read()
    if len(content) > 4 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="file too large")
    try:
        img = Image.open(io.BytesIO(content))
    except Exception as exc:
        raise HTTPException(status_code=400, detail="invalid image data") from exc
    img = ImageOps.fit(img, (256, 256))
    img = img.convert("RGB")
    fname = f"{generate_id()}.jpg"
    dest = UPLOAD_DIR / fname
    try:
        img.save(dest, format="JPEG", quality=85)
    except OSError as exc:
        raise HTTPException(status_code=500, detail="failed to save image") from exc
    return f"/static/profile/{fname}"


def _remove_old_photo(path: str | None) -> None:
    """Delete an existing profile photo if it exists."""
    if not path:
        return
    old_path = BASE_DIR / path.lstrip("/")
    if not old_path.exists():
        return
    if UPLOAD_DIR not in old_path.resolve().parents:
        raise HTTPException(status_code=400, detail="invalid photo path")
    try:
        old_path.unlink()
    except OSError as exc:
        raise HTTPException(status_code=500, detail="failed to remove photo") from exc


@router.get("/profile", response_class=HTMLResponse)
async def profile_page(request: Request) -> HTMLResponse:
    """Render the profile management page."""
    user = request.session.get("user", {})
    meta = {}
    username = user.get("name")
    if username:
        meta = cfg.get("user_metadata", {}).get(username, {})
    return templates.TemplateResponse(
        "profile.html", {"request": request, "cfg": cfg, "meta": meta}
    )


@router.post("/profile")
async def update_profile(
    name: str = Form(...),
    password: str | None = Form(None),
    photo: UploadFile | None = File(None),
    remove_photo: bool = Form(False),
) -> JSONResponse:
    """Update user profile information."""
    cfg["user_name"] = name
    if password:
        cfg["user_password"] = password
    if remove_photo:
        old = cfg.pop("profile_photo", None)
        _remove_old_photo(old)
    elif photo and photo.filename:
        new_path = await _process_photo(photo)
        old = cfg.get("profile_photo")
        if old:
            _remove_old_photo(old)
        cfg["profile_photo"] = f"{new_path}?v={int(time.time())}"
    return JSONResponse({"saved": True})


@router.get("/api/profile/widgets")
async def get_widget_prefs() -> JSONResponse:
    """Return saved dashboard widget preferences."""
    return JSONResponse({"widgets": cfg.get("widget_prefs", {})})


@router.post("/api/profile/widgets")
async def save_widget_prefs(prefs: Dict[str, bool] = Body(...)) -> JSONResponse:
    """Persist dashboard widget preferences."""
    cfg["widget_prefs"] = prefs
    return JSONResponse({"saved": True})


@router.get("/profile/visibility", response_class=HTMLResponse)
async def profile_visibility(request: Request) -> HTMLResponse:
    """Display profile visibility options."""
    return templates.TemplateResponse(
        "profile_visibility.html", {"request": request, "cfg": cfg}
    )


@router.get("/profile/privacy", response_class=HTMLResponse)
async def privacy_page(request: Request) -> HTMLResponse:
    """Display privacy options."""
    return templates.TemplateResponse("privacy.html", {"request": request, "cfg": cfg})
