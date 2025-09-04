"""Face management and search routes."""

from __future__ import annotations

import base64
import json
import os
import time
import uuid
from pathlib import Path

import cv2
import numpy as np
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import JSONResponse
from fastapi_csrf_protect import CsrfProtect

try:  # pragma: no cover - fallback for tests without full library
    from fastapi_csrf_protect.exceptions import CsrfProtectError
except Exception:  # pragma: no cover

    class CsrfProtectError(Exception):
        """Fallback CSRF error when library exceptions are unavailable."""

        pass


from loguru import logger
from pydantic_settings import BaseSettings

from config import FACE_THRESHOLDS, config
from modules import face_db
from modules.utils import require_admin, require_viewer
from utils.audit import log_audit
from utils.deps import get_cameras
from utils.ids import generate_id
from utils.image import decode_base64_image
from utils.time import format_ts

from ..visitor_utils import visitor_disabled_response
from . import (
    _face_search_enabled,
    _search_embeddings,
    _trim_visitor_logs,
    face_app,
    get_context,
)

ctx = get_context()
redis = ctx.redis
templates = ctx.templates

router = APIRouter()

AUDIT_LOG_KEY = "audit:faces"


def _log_face_action(action: str, user: dict | None, details: str) -> None:
    """Record face database actions for auditing."""
    username = user.get("username", "") if isinstance(user, dict) else ""
    entry = {
        "action": action,
        "user": username,
        "details": details,
        "ts": int(time.time()),
    }
    try:
        redis.lpush(AUDIT_LOG_KEY, json.dumps(entry))
        redis.ltrim(AUDIT_LOG_KEY, 0, 99)
    except Exception:  # pragma: no cover - logging should not fail
        log_audit(action, username, **{"details": details})


# Upload validation settings
MAX_UPLOAD_SIZE = 5 * 1024 * 1024  # 5 MB
ALLOWED_MIME_TYPES = {"image/jpeg", "image/png"}
ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png"}


async def _validate_photo(photo: UploadFile | None) -> tuple[bytes | None, str | None]:
    """Validate uploaded image file and return bytes or error message."""
    if photo is None:
        return None, None
    ext = Path(photo.filename or "").suffix.lower()
    if photo.content_type not in ALLOWED_MIME_TYPES or ext not in ALLOWED_EXTENSIONS:
        return None, "Unsupported file type. Only JPEG and PNG images are allowed."
    data = await photo.read(MAX_UPLOAD_SIZE + 1)
    if len(data) > MAX_UPLOAD_SIZE:
        return None, "File too large. Maximum size is 5 MB."
    return data, None


def _validate_captured(captured: str) -> tuple[bytes | None, str | None]:
    """Validate captured base64 image and return bytes or error message."""
    if not captured:
        return None, None
    try:
        header, _ = captured.split(",", 1)
    except ValueError:
        return None, "Invalid captured image."
    mime = header.split(";")[0].split(":")[-1]
    if mime not in ALLOWED_MIME_TYPES:
        return None, "Unsupported file type. Only JPEG and PNG images are allowed."
    try:
        data = decode_base64_image(captured)
    except ValueError:
        return None, "Invalid captured image."
    if len(data) > MAX_UPLOAD_SIZE:
        return None, "File too large. Maximum size is 5 MB."
    return data, None


def _validate_face_id(face_id: str) -> str:
    """Ensure the provided face ID is a 32-character hexadecimal string."""
    fid = (face_id or "").strip().lower()
    try:
        uuid.UUID(hex=fid)
    except Exception as exc:
        raise HTTPException(status_code=400, detail="invalid_face_id") from exc
    return fid


class CsrfSettings(BaseSettings):
    """Configuration for CSRF protection."""

    secret_key: str


@CsrfProtect.load_config
def get_csrf_config() -> CsrfSettings:
    """Provide secret key for CSRF token generation."""

    secret = os.getenv("CSRF_SECRET_KEY") or config.get("secret_key", "change-me")
    return CsrfSettings(secret_key=secret)


csrf_protect = CsrfProtect()

# Redis hash mapping gate-pass or visitor IDs to face IDs
VISITOR_INDEX_KEY = "visitor:face_ids"


def _index_face(face_id: str, visitor_id: str | None, gate_pass_id: str | None) -> None:
    """Add visitor identifiers to the lookup index."""
    mapping: dict[str, str] = {}
    if visitor_id:
        mapping[visitor_id.lower()] = face_id
    if gate_pass_id:
        mapping[gate_pass_id.lower()] = face_id
    if mapping:
        redis.hset(VISITOR_INDEX_KEY, mapping=mapping)


def _remove_from_index(visitor_id: str | None, gate_pass_id: str | None) -> None:
    """Remove visitor identifiers from the lookup index."""
    fields = [f.lower() for f in (visitor_id, gate_pass_id) if f]
    if fields:
        redis.hdel(VISITOR_INDEX_KEY, *fields)


def _face_counts() -> dict[str, int]:
    """Return counts of faces grouped by status."""
    return {
        "known_count": redis.scard("face:known_ids"),
        "unregistered_count": redis.scard("face:unregistered_ids"),
        "pending_count": redis.scard("face:pending_ids"),
        "deleted_count": redis.scard("face:deleted_ids"),
    }


@router.get("/api/face/sources")
async def api_face_sources(cams: list = Depends(get_cameras)):
    sources = [
        {"id": str(c["id"]), "label": c.get("name") or f"Camera {c['id']}"}
        for c in cams
    ]
    sources.append({"id": "manual", "label": "Manual Upload"})
    return {"sources": sources}


@router.get("/face_details/{face_id}")
async def face_details(face_id: str, user=Depends(require_admin)):
    """Return metadata for a known face."""
    if not ctx.config.get("features", {}).get("visitor_mgmt"):
        return visitor_disabled_response()
    face_id = _validate_face_id(face_id)
    fields = {
        k.decode() if isinstance(k, bytes) else k: (
            v.decode() if isinstance(v, bytes) else v
        )
        for k, v in redis.hgetall(f"face:known:{face_id}").items()
    }
    if not fields:
        return JSONResponse({"error": "not_found"}, status_code=404)
    created_at = fields.get("created_at")
    date_str = ""
    if created_at:
        try:
            date_str = format_ts(int(created_at), "%d-%b-%Y")
        except Exception:
            date_str = ""
    conf_raw = fields.get("confidence")
    try:
        confidence = float(conf_raw) if conf_raw is not None else 0.0
    except ValueError:
        confidence = 0.0
    result = {
        "name": fields.get("name", ""),
        "gate_pass_id": fields.get("gate_pass_id", ""),
        "visitor_type": fields.get("visitor_type", ""),
        "date": date_str,
        "confidence": confidence,
        "model_version": fields.get("model_version", ""),
    }
    vid = fields.get("visitor_id")
    if vid:
        result["visitor_id"] = vid
    # return any recorded embedding version
    result["embedding_version"] = fields.get("embedding_version", "")

    # gather related ids sharing the same name
    ids = [face_id]
    name = fields.get("name")
    if name:
        for fid in redis.smembers("face:known_ids"):
            fid_str = fid.decode() if isinstance(fid, bytes) else fid
            if fid_str == face_id:
                continue
            nm = redis.hget(f"face:known:{fid_str}", "name")
            if isinstance(nm, bytes):
                nm = nm.decode()
            if nm == name:
                ids.append(fid_str)
    result["ids"] = ids

    # collect recent images from visitor log history
    images: list[str] = []
    for raw in redis.zrevrange("visitor_logs", 0, -1):
        try:
            obj = json.loads(raw if isinstance(raw, str) else raw.decode())
        except Exception:
            continue
        if obj.get("face_id") != face_id:
            continue
        img = obj.get("image")
        if img:
            images.append(img)
        if len(images) >= 10:
            break
    result["images"] = images
    return result


@router.post("/face_details/{face_id}")
async def update_face_details(
    face_id: str,
    name: str = Form(""),
    gate_pass_id: str = Form(""),
    visitor_id: str = Form(""),
    visitor_type: str = Form(""),
    csrf_token: str = Form(...),
    csrf_protect: CsrfProtect = Depends(),
    user=Depends(require_admin),
):
    """Update metadata for a known face."""
    if not ctx.config.get("features", {}).get("visitor_mgmt"):
        return visitor_disabled_response()
    try:
        csrf_protect.validate_csrf_in_cookies(csrf_token)
    except CsrfProtectError:
        return JSONResponse({"error": "invalid_csrf"}, status_code=403)

    prev_gp = redis.hget(f"face:known:{face_id}", "gate_pass_id")
    prev_vid = redis.hget(f"face:known:{face_id}", "visitor_id")
    if isinstance(prev_gp, bytes):
        prev_gp = prev_gp.decode()
    if isinstance(prev_vid, bytes):
        prev_vid = prev_vid.decode()
    mapping: dict[str, str] = {}
    if name:
        mapping["name"] = name
    if gate_pass_id:
        mapping["gate_pass_id"] = gate_pass_id
    if visitor_id:
        mapping["visitor_id"] = visitor_id
    if visitor_type:
        mapping["visitor_type"] = visitor_type
    if not mapping:
        return {"saved": False}
    redis.hset(f"face:known:{face_id}", mapping=mapping)
    new_vid = mapping.get("visitor_id", prev_vid)
    new_gp = mapping.get("gate_pass_id", prev_gp)
    _remove_from_index(prev_vid, prev_gp)
    _index_face(face_id, new_vid, new_gp)
    redis.publish("faces_updated", face_id)
    return {"saved": True}


async def _extract_image(photo: UploadFile | None, captured: str) -> bytes:
    """Return JPEG bytes for a single detected face.

    Raises ``ValueError`` with an explanatory message on validation errors or
    when a single face cannot be determined.
    """

    img_bytes, error = _validate_captured(captured)
    if not img_bytes and not error:
        img_bytes, error = await _validate_photo(photo)
    if error or not img_bytes or face_app is None:
        raise ValueError(error or "Invalid image")
    arr = cv2.imdecode(np.frombuffer(img_bytes, np.uint8), cv2.IMREAD_COLOR)
    if arr is None:
        raise ValueError("Invalid image")
    rgb = cv2.cvtColor(arr, cv2.COLOR_BGR2RGB)
    if captured and not photo:
        crop = rgb
    else:
        faces = face_app.get(rgb)
        if len(faces) != 1:
            raise ValueError("Exactly one face required")
        x1, y1, x2, y2 = [int(v) for v in faces[0].bbox]
        crop = rgb[y1:y2, x1:x2]
    bgr = cv2.cvtColor(crop, cv2.COLOR_RGB2BGR)
    return cv2.imencode(".jpg", bgr)[1].tobytes()


def _store_face_image(face_id: str, crop_bytes: bytes) -> Path:
    """Persist ``crop_bytes`` to disk and return the file path."""

    out_dir = Path("public") / "face_db"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{face_id}.jpg"
    out_path.write_bytes(crop_bytes)
    return out_path


def _insert_face_record(
    face_id: str, crop_bytes: bytes, *, merge: bool = False, force_new: bool = False
) -> list[dict]:
    """Insert a face record or return duplicate matches.

    When ``merge`` is true, the new image is merged with any existing record for
    ``face_id``. For normal inserts, duplicate detection is performed unless
    ``force_new`` is supplied. Any detected matches are returned and insertion is
    skipped.
    """

    if merge:
        try:
            face_db.insert(crop_bytes, face_id, source="manual", merge_on_match=True)
        except Exception:  # pragma: no cover - defensive
            logger.exception("face_db.insert failed for face_id=%s", face_id)
        return []

    matches: list[dict] = []
    if not force_new:
        try:
            matches = face_db.search_faces(crop_bytes, 1, FACE_THRESHOLDS.db_duplicate)
        except Exception:  # pragma: no cover - defensive
            logger.exception("face_db.search_faces failed for face_id=%s", face_id)
            matches = []
    if matches:
        return matches

    out_path = _store_face_image(face_id, crop_bytes)
    redis.hset(
        f"face:unregistered:{face_id}",
        mapping={
            "image_path": str(out_path),
            "created_at": str(int(time.time())),
        },
    )
    redis.sadd("face:unregistered_ids", face_id)
    face_db.insert(crop_bytes, face_id, source="manual", threshold=1.1)
    return []


@router.post("/reembed_face/{face_id}")
async def reembed_face_route(face_id: str, user=Depends(require_admin)):
    """Recompute and update embedding for ``face_id``."""
    if not ctx.config.get("features", {}).get("visitor_mgmt"):
        return visitor_disabled_response()
    face_id = _validate_face_id(face_id)
    try:
        face_db.reembed_face(face_id)
        return {"reembedded": True}
    except Exception as exc:  # pragma: no cover - defensive
        logger.exception("reembed failed: {}", exc)
        return JSONResponse({"reembedded": False}, status_code=400)


@router.post("/merge_faces")
async def merge_faces(
    name: str = Form(...),
    face_ids: str = Form(...),
    csrf_token: str = Form(...),
    csrf_protect: CsrfProtect = Depends(),
    user=Depends(require_admin),
):
    """Merge multiple face IDs into a single visitor name."""
    if not ctx.config.get("features", {}).get("visitor_mgmt"):
        return visitor_disabled_response()
    try:
        csrf_protect.validate_csrf_in_cookies(csrf_token)
    except CsrfProtectError:
        return JSONResponse({"error": "invalid_csrf"}, status_code=403)
    ids = [f for f in face_ids.split(",") if f]
    for fid in ids:
        _validate_face_id(fid)
    if not ids:
        return {"saved": False}
    new_id = ids[0]
    embeddings: list = []
    img_path = None
    merged_gp = None
    merged_vid = None
    for fid in ids:
        try:
            emb, path, _ = face_db.fetch_known_face(fid)
        except Exception:
            emb, path = None, None
        if emb is None:
            record = redis.hget(f"face_db:manual:{fid}", "embedding")
            if record:
                try:
                    emb = json.loads(
                        record if isinstance(record, str) else record.decode()
                    )
                except Exception:
                    emb = []
            data = {
                k.decode() if isinstance(k, bytes) else k: (
                    v.decode() if isinstance(v, bytes) else v
                )
                for k, v in redis.hgetall(f"face:unregistered:{fid}").items()
            }
            if img_path is None:
                img_path = data.get("image_path") or redis.hget(
                    f"face_db:manual:{fid}", "image_path"
                )
                if isinstance(img_path, bytes):
                    img_path = img_path.decode()
        else:
            data = {
                k.decode() if isinstance(k, bytes) else k: (
                    v.decode() if isinstance(v, bytes) else v
                )
                for k, v in redis.hgetall(f"face:known:{fid}").items()
            }
            if img_path is None and path:
                img_path = path
        vid = data.get("visitor_id")
        gp_id = data.get("gate_pass_id")
        if merged_vid is None and vid:
            merged_vid = vid
        if merged_gp is None and gp_id:
            merged_gp = gp_id
        _remove_from_index(vid, gp_id)
        if emb:
            embeddings.append(emb)
        redis.delete(f"face:unregistered:{fid}")
        redis.srem("face:unregistered_ids", fid)
        redis.delete(f"face:known:{fid}")
        redis.srem("face:known_ids", fid)
        face_db.remove_from_index(fid)
    if not embeddings:
        return {"saved": False}
    centroid = np.mean(embeddings, axis=0)
    mapping = {
        "name": name,
        "embedding": json.dumps(centroid.tolist()),
        "image_path": img_path or "",
        "created_at": str(int(time.time())),
    }
    if merged_vid:
        mapping["visitor_id"] = merged_vid
    if merged_gp:
        mapping["gate_pass_id"] = merged_gp
    redis.hset(f"face:known:{new_id}", mapping=mapping)
    _index_face(new_id, merged_vid, merged_gp)
    redis.sadd("face:known_ids", new_id)
    redis.publish("faces_updated", new_id)
    if img_path and Path(img_path).exists():
        with open(img_path, "rb") as f:
            b64 = base64.b64encode(f.read()).decode()
        redis.hset("known_faces", name, b64)
    redis.hset("known_visitors", name, json.dumps(centroid.tolist()))
    face_db.add_to_index(new_id, centroid)
    entries = redis.zrevrange("visitor_logs", 0, -1)
    for e in entries:
        obj = json.loads(e)
        if obj["face_id"] in ids:
            obj["name"] = name
            obj["face_id"] = new_id
            redis.zadd("visitor_logs", {json.dumps(obj): obj["ts"]})

        await _trim_visitor_logs()
    _log_face_action("merge", user, f"{','.join(ids)}->{new_id}")
    return {"saved": True}


@router.post("/delete_faces")
async def delete_faces(
    face_ids: str = Form(...),
    reason: str = Form(""),
    user=Depends(require_admin),
):
    """Remove faces from both known and unregistered sets.

    The optional ``reason`` field allows callers to supply context for the
    deletion. Empty reasons are ignored.
    """

    if not ctx.config.get("features", {}).get("visitor_mgmt"):
        return visitor_disabled_response()
    ids = [f for f in face_ids.split(",") if f]
    for fid in ids:
        _validate_face_id(fid)
    removed: list[str] = []
    ts = str(int(time.time()))
    for fid in ids:
        data = {
            k.decode() if isinstance(k, bytes) else k: (
                v.decode() if isinstance(v, bytes) else v
            )
            for k, v in redis.hgetall(f"face:known:{fid}").items()
        }
        if not data:
            data = {
                k.decode() if isinstance(k, bytes) else k: (
                    v.decode() if isinstance(v, bytes) else v
                )
                for k, v in redis.hgetall(f"face:unregistered:{fid}").items()
            }
        name = data.get("name")
        if name:
            redis.hdel("known_faces", name)
            redis.hdel("known_visitors", name)

        # move record to deleted set for potential restoration
        img_path = data.get("image_path")
        data["deleted_at"] = ts
        if reason:
            data["reason"] = reason
        data["deleted_by"] = user.get("name", "")
        redis.hset(f"face:deleted:{fid}", mapping=data)
        redis.sadd("face:deleted_ids", fid)
        redis.expire(f"face:deleted:{fid}", 30 * 24 * 3600)

        _remove_from_index(data.get("visitor_id"), data.get("gate_pass_id"))
        redis.delete(f"face:known:{fid}")
        redis.srem("face:known_ids", fid)
        redis.delete(f"face:unregistered:{fid}")
        redis.srem("face:unregistered_ids", fid)
        face_db.remove_from_index(fid)
        removed.append(fid)
    if removed:
        redis.publish("faces_updated", ",".join(removed))
    _log_face_action("delete", user, ",".join(removed), reason=reason)

    return {"deleted": bool(removed)}


@router.post("/reembed_face")
async def reembed_face(face_id: str = Form(...)):
    """Queue a re-embedding job for ``face_id``."""
    if not ctx.config.get("features", {}).get("visitor_mgmt"):
        return visitor_disabled_response()
    face_id = _validate_face_id(face_id)
    face_db.queue_reembed(face_id)
    return {"queued": True}


