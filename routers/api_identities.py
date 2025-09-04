"""API endpoints for identity profiles."""

from __future__ import annotations

from fastapi import APIRouter, Body, HTTPException
from fastapi.responses import JSONResponse
from loguru import logger

router = APIRouter()

logger = logger.bind(module="api_identities")

redis_client = None


def init_context(cfg: dict, redis) -> None:
    """Initialize Redis client."""
    global redis_client
    redis_client = redis


@router.get("/api/identities/{identity_id}")
def get_identity(identity_id: str):
    r = redis_client
    if r is None:
        return JSONResponse({"error": "unavailable"}, status_code=500)
    data = r.hgetall(f"identity:{identity_id}")
    if not data:
        raise HTTPException(status_code=404, detail="identity_not_found")
    tags = data.get("tags", "")
    faces = []
    for fid in r.lrange(f"identity:{identity_id}:faces", 0, -1):
        fdata = r.hgetall(f"identity_face:{fid}")
        faces.append(
            {
                "id": fid,
                "url": fdata.get("url", ""),
                "is_primary": fid == data.get("primary_face_id"),
            }
        )
    visits = r.lrange(f"identity:{identity_id}:visits", 0, -1)
    cams = list(r.smembers(f"identity:{identity_id}:cameras"))
    return {
        "id": identity_id,
        "name": data.get("name", ""),
        "company": data.get("company", ""),
        "tags": tags.split(",") if tags else [],
        "faces": faces,
        "visits": visits,
        "cameras": cams,
    }


@router.post("/api/identities/{identity_id}")
def update_identity(identity_id: str, payload: dict = Body(...)):
    r = redis_client
    if r is None:
        return JSONResponse({"error": "unavailable"}, status_code=500)
    fields: dict[str, str] = {}
    for key in ("name", "company"):
        if key in payload:
            fields[key] = str(payload[key])
    if "tags" in payload:
        tags = payload["tags"]
        if isinstance(tags, list):
            tags = ",".join(tags)
        fields["tags"] = str(tags)
    if fields:
        r.hset(f"identity:{identity_id}", mapping=fields)
    return {"updated": True}


@router.delete("/api/identities/{identity_id}/faces/{face_id}")
def remove_face(identity_id: str, face_id: str):
    r = redis_client
    if r is None:
        return JSONResponse({"error": "unavailable"}, status_code=500)
    r.lrem(f"identity:{identity_id}:faces", 0, face_id)
    r.delete(f"identity_face:{face_id}")
    if r.hget(f"identity:{identity_id}", "primary_face_id") == face_id:
        r.hdel(f"identity:{identity_id}", "primary_face_id")
    return {"removed": True}


@router.post("/api/identities/{identity_id}/faces/{face_id}/primary")
def set_primary_face(identity_id: str, face_id: str):
    r = redis_client
    if r is None:
        return JSONResponse({"error": "unavailable"}, status_code=500)
    r.hset(f"identity:{identity_id}", "primary_face_id", face_id)
    return {"primary_set": True}

