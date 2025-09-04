"""API endpoints for managing training jobs."""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, RedirectResponse

from modules.utils import require_roles

router = APIRouter()

redis_client = None


# init_context routine
def init_context(cfg: dict, r) -> None:
    global redis_client
    redis_client = r


@router.post("/api/training/start")
async def start_training(request: Request):
    res = require_roles(request, ["admin"])
    if isinstance(res, RedirectResponse):
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    if redis_client is None:
        return JSONResponse({"error": "unavailable"}, status_code=500)
    redis_client.set("training:status", "running")
    return {"started": True}


@router.get("/api/training/status")
async def training_status(request: Request):
    res = require_roles(request, ["admin", "viewer"])
    if isinstance(res, RedirectResponse):
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    if redis_client is None:
        return JSONResponse({"error": "unavailable"}, status_code=500)
    status = redis_client.get("training:status") or b"idle"
    if isinstance(status, bytes):
        status = status.decode()
    return {"status": status}
