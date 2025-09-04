"""API endpoints for face database operations."""

from __future__ import annotations

import asyncio
import base64
import json
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Body, Depends, File, Form, Query, Request, UploadFile
from fastapi.responses import JSONResponse, StreamingResponse
from loguru import logger

from modules import face_db
from modules.utils import require_roles
from utils.api_errors import error_response
from utils.deps import get_cameras

router = APIRouter()

logger = logger.bind(module="api_faces")

AUDIT_STREAM = "audit:faces"


def _log_face_action(action: str, **fields: Any) -> None:
    """Record face-related actions to the audit stream."""
    r = face_db.redis_client
    if r is None:
        return
    entry = {"action": action, "ts": str(int(time.time()))}
    entry.update({k: str(v) for k, v in fields.items()})
    try:
        r.xadd(AUDIT_STREAM, entry, maxlen=1000, approximate=True)
    except Exception:
        logger.exception("Failed to append audit entry", action=action)


def _encode_cursor(value: Any, fid: str, direction: str) -> str:
    payload = json.dumps({"v": value, "id": fid, "d": direction})
    return base64.urlsafe_b64encode(payload.encode()).decode().rstrip("=")


def _decode_cursor(token: str) -> tuple[Any | None, str | None, str]:
    try:
        pad = "=" * (-len(token) % 4)
        data = base64.urlsafe_b64decode(token + pad).decode()
        obj = json.loads(data)
        return obj.get("v"), obj.get("id"), obj.get("d", "next")
    except Exception:
        return None, None, "next"


# init_context routine
def init_context(cfg: dict, redis_client) -> None:
    """Initialize helper modules."""
    face_db.init(cfg, redis_client)


@router.post("/api/faces/add")
async def api_add_face(
    visitor_id: str = Form(...),
    image: UploadFile = File(...),
    merge_on_match: bool = Form(True),
    threshold: float = Form(0.95),
):
    try:
        data = await image.read()
        if not face_db.add_face_if_single_detected(
            data, visitor_id, merge_on_match=merge_on_match, threshold=threshold
        ):
            return error_response(
                "multiple_faces_detected", "Multiple faces detected", status_code=400
            )
    except Exception:
        logger.exception("Failed to add face", visitor_id=visitor_id)
        return error_response(
            "processing_failed", "Failed to add face", status_code=500
        )
    _log_face_action("attach", visitor_id=visitor_id)
    return {"added": True}


@router.post("/api/faces/search")
async def api_search_face(
    image: UploadFile = File(...),
    top_k: int = Form(5),
    threshold: float | None = Form(None),
):
    try:
        data = await image.read()
        results = face_db.search_faces(data, top_k, threshold)
    except Exception:
        logger.exception("Face search failed")
    return error_response("processing_failed", "Face search failed", status_code=500)
    return {"matches": results}


@router.get("/api/faces")
async def get_faces(
    request: Request,
    status: str = Query("known"),
    q: str | None = None,
    from_: str | None = Query(None, alias="from"),
    to: str | None = None,
    camera_ids: list[str] | None = Query(None),
    sort: str = "last_seen_desc",
    limit: int = Query(20, ge=1, le=100),
    cursor: str | None = None,
    cams: list = Depends(get_cameras),
):
    res = require_roles(request, ["admin", "viewer"])
    if isinstance(res, RedirectResponse):
        return JSONResponse({"error": "unauthorized"}, status_code=401)

    r = face_db.redis_client
    if r is None:
        return JSONResponse({"error": "unavailable"}, status_code=500)

    if not 1 <= limit <= 100:
        return JSONResponse({"error": "invalid_limit"}, status_code=422)

    set_map = {
        "known": "face:known_ids",
        "unregistered": "face:unregistered_ids",
        "pending": "face:pending_ids",
        "deleted": "face:deleted_ids",
    }
    set_key = set_map.get(status)
    if not set_key:
        return JSONResponse({"error": "invalid_status"}, status_code=400)

    cam_map = {str(c["id"]): c.get("name") or f"Camera {c['id']}" for c in cams}

    ids = [i.decode() if isinstance(i, bytes) else i for i in r.smembers(set_key)]
    items: list[dict[str, Any]] = []
    from_ts: int | None = None
    to_ts: int | None = None
    if from_:
        try:
            from_ts = int(datetime.fromisoformat(from_).timestamp())
        except ValueError:
            return JSONResponse({"error": "invalid_from"}, status_code=422)
    if to:
        try:
            to_ts = int(datetime.fromisoformat(to).timestamp())
        except ValueError:
            return JSONResponse({"error": "invalid_to"}, status_code=422)

    if q:
        q = re.sub(r"[^\w\s-]", "", q).strip().lower()

    for fid in ids:
        raw = r.hgetall(f"face:{status}:{fid}")
        fields = {
            k.decode() if isinstance(k, bytes) else k: (
                v.decode() if isinstance(v, bytes) else v
            )
            for k, v in raw.items()
        }
        name = fields.get("name", "")
        if q and q not in name.lower():
            continue
        last_seen = int(fields.get("last_seen_at") or fields.get("created_at") or 0)
        first_seen = int(fields.get("first_seen_at") or fields.get("created_at") or 0)
        if from_ts and last_seen < from_ts:
            continue
        if to_ts and last_seen > to_ts:
            continue
        cam_id = fields.get("camera_id") or fields.get("device_id") or ""
        if camera_ids and cam_id not in camera_ids:
            continue
        img_path = fields.get("image_path", "")
        thumb = f"/faces/{Path(img_path).name}" if img_path else ""
        captured = int(fields.get("captured_at") or fields.get("created_at") or 0)
        candidates: list[dict[str, Any]] = []
        emb = fields.get("embedding")
        if emb:
            try:
                vec = np.array(json.loads(emb), dtype="float32")
                cands = face_db.search_embedding(vec, top_k=4)
                candidates = [c for c in cands if c.get("id") != fid][:3]
            except Exception:
                candidates = []
        item = {
            "id": fid,
            "name": name,
            "thumbnail_url": thumb,
            "last_seen_at": last_seen,
            "first_seen_at": first_seen,
            "captured_at": captured,
            "similarity_candidates": candidates,
            "camera": (
                {"id": cam_id, "label": cam_map.get(str(cam_id), "")}
                if cam_id
                else None
            ),
            "status": status,
        }
        items.append(item)

    total = len(items)

    sort_field = "last_seen_at"
    reverse = False
    if sort == "last_seen_asc":
        sort_field = "last_seen_at"
    elif sort == "last_seen_desc":
        sort_field = "last_seen_at"
        reverse = True
    elif sort == "first_seen_asc":
        sort_field = "first_seen_at"
    elif sort == "first_seen_desc":
        sort_field = "first_seen_at"
        reverse = True
    elif sort == "name_asc":
        sort_field = "name"
    elif sort == "name_desc":
        sort_field = "name"
        reverse = True
    else:
        sort = "last_seen_desc"
        reverse = True
    items.sort(key=lambda x: (x[sort_field], x["id"]), reverse=reverse)

    keys = [(i[sort_field], i["id"]) for i in items]
    page: list[dict[str, Any]] = []
    start = 0
    if cursor:
        val, cid, direction = _decode_cursor(cursor)
        if val is None or cid is None or direction not in {"next", "prev"}:
            return JSONResponse({"error": "invalid_cursor"}, status_code=400)
        cursor_key = (val, cid)
        if direction == "prev":
            if reverse:
                idx = next(
                    (i for i, k in enumerate(keys) if k <= cursor_key), len(keys)
                )
            else:
                idx = next(
                    (i for i, k in enumerate(keys) if k >= cursor_key), len(keys)
                )
            end = idx
            start = max(0, end - limit)
            page = items[start:end]
        else:
            if reverse:
                start = next(
                    (i for i, k in enumerate(keys) if k < cursor_key), len(keys)
                )
            else:
                start = next(
                    (i for i, k in enumerate(keys) if k > cursor_key), len(keys)
                )
            page = items[start : start + limit]
    else:
        page = items[:limit]
    end = start + len(page)

    next_cursor = (
        _encode_cursor(page[-1][sort_field], page[-1]["id"], "next")
        if end < len(items) and page
        else None
    )
    prev_cursor = (
        _encode_cursor(page[0][sort_field], page[0]["id"], "prev")
        if start > 0 and page
        else None
    )

    counts = {
        "known_count": r.scard("face:known_ids"),
        "unregistered_count": r.scard("face:unregistered_ids"),
        "pending_count": r.scard("face:pending_ids"),
        "deleted_count": r.scard("face:deleted_ids"),
    }
    resp: dict[str, Any] = {"faces": page, "counts": counts, "total_estimate": total}
    if next_cursor:
        resp["next_cursor"] = next_cursor
    if prev_cursor:
        resp["prev_cursor"] = prev_cursor
    return resp


@router.post("/api/faces/{face_id}/attach")
async def attach_face(face_id: str, request: Request, payload: dict = Body(...)):
    res = require_roles(request, ["admin"])
    if isinstance(res, RedirectResponse):
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    identity_id = payload.get("identity_id")
    if not identity_id:
        return JSONResponse({"error": "missing_identity_id"}, status_code=422)
    r = face_db.redis_client
    if r is None:
        return JSONResponse({"error": "unavailable"}, status_code=500)
    r.hset(f"face:known:{face_id}", "identity_id", identity_id)
    r.sadd(f"identity:{identity_id}:faces", face_id)
    return {"attached": True}


@router.post("/api/faces/{face_id}/status")
async def update_face_status(face_id: str, request: Request, payload: dict = Body(...)):
    res = require_roles(request, ["admin"])
    if isinstance(res, RedirectResponse):
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    new_status = payload.get("status")
    allowed = {"known", "unregistered", "pending", "deleted"}
    if new_status not in allowed:
        return JSONResponse({"error": "invalid_status"}, status_code=422)
    r = face_db.redis_client
    if r is None:
        return JSONResponse({"error": "unavailable"}, status_code=500)
    current = next((s for s in allowed if r.sismember(f"face:{s}_ids", face_id)), None)
    if not current:
        return JSONResponse({"error": "not_found"}, status_code=404)
    if current == new_status:
        return {"status": current}
    data = r.hgetall(f"face:{current}:{face_id}")
    pipe = r.pipeline()
    pipe.delete(f"face:{current}:{face_id}")
    pipe.srem(f"face:{current}_ids", face_id)
    if data:
        pipe.hset(f"face:{new_status}:{face_id}", mapping=data)
    pipe.sadd(f"face:{new_status}_ids", face_id)
    pipe.execute()
    return {"status": new_status}


@router.delete("/api/faces/{face_id}")
async def delete_face(face_id: str, request: Request):
    res = require_roles(request, ["admin"])
    if isinstance(res, RedirectResponse):
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    r = face_db.redis_client
    if r is None:
        return JSONResponse({"error": "unavailable"}, status_code=500)
    for status_key in ["known", "unregistered", "pending", "deleted"]:
        r.delete(f"face:{status_key}:{face_id}")
        r.srem(f"face:{status_key}_ids", face_id)
    return {"deleted": True}


@router.post("/api/faces/{face_id}/ban")
async def ban_face(face_id: str, request: Request):
    res = require_roles(request, ["admin"])
    if isinstance(res, RedirectResponse):
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    r = face_db.redis_client
    if r is None:
        return JSONResponse({"error": "unavailable"}, status_code=500)
    r.sadd("face:banned_ids", face_id)
    r.hset(f"face:known:{face_id}", "banned", 1)
    return {"banned": True}


@router.get("/api/faces/stats")
async def api_face_stats() -> dict:
    """Return live counts of faces grouped by status."""
    r = face_db.redis_client
    if r is None:
        return JSONResponse({"error": "stats_unavailable"}, status_code=500)
    try:
        return {
            "known_count": r.scard("face:known_ids"),
            "unregistered_count": r.scard("face:unregistered_ids"),
            "pending_count": r.scard("face:pending_ids"),
            "deleted_count": r.scard("face:deleted_ids"),
        }
    except Exception:
        logger.exception("Failed to fetch face stats")
        return JSONResponse({"error": "stats_unavailable"}, status_code=500)


@router.get("/sse/faces")
async def sse_faces() -> StreamingResponse:
    """Stream face count updates and training progress via SSE."""
    r = face_db.redis_client
    if r is None:
        return JSONResponse({"error": "unavailable"}, status_code=500)

    async def event_source() -> Any:
        pubsub = r.pubsub(ignore_subscribe_messages=True)
        pubsub.subscribe("faces_updated", "training_progress")
        try:
            while True:
                msg = await asyncio.to_thread(pubsub.get_message, timeout=5.0)
                if msg and msg.get("type") == "message":
                    chan = (
                        msg["channel"].decode()
                        if isinstance(msg["channel"], bytes)
                        else msg["channel"]
                    )
                    data = (
                        msg["data"].decode()
                        if isinstance(msg["data"], bytes)
                        else msg["data"]
                    )
                    if chan == "faces_updated":
                        counts = {
                            "known_count": await asyncio.to_thread(
                                r.scard, "face:known_ids"
                            ),
                            "unregistered_count": await asyncio.to_thread(
                                r.scard, "face:unregistered_ids"
                            ),
                            "pending_count": await asyncio.to_thread(
                                r.scard, "face:pending_ids"
                            ),
                            "deleted_count": await asyncio.to_thread(
                                r.scard, "face:deleted_ids"
                            ),
                        }
                        payload = {"type": "counts", **counts}
                    else:
                        payload = {"type": "training", "progress": data}
                    yield f"data: {json.dumps(payload)}\n\n"
                else:
                    yield ": ping\n\n"
        finally:
            try:
                pubsub.unsubscribe("faces_updated", "training_progress")
                pubsub.close()
            except Exception:
                pass

    return StreamingResponse(
        event_source(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
