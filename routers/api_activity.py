"""API endpoint for recent detection activity."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse
from loguru import logger

from utils.deps import get_redis

router = APIRouter()

STREAM_KEY = "activity:decisions"


@router.get("/api/activity")
async def get_activity(
    limit: int = Query(20, ge=1, le=100),
    cursor: str | None = None,
    redis=Depends(get_redis),
) -> dict | JSONResponse:
    try:
        start = cursor or "+"
        entries = redis.xrevrange(STREAM_KEY, max=start, min="-", count=limit)
        items: list[dict[str, Any]] = []
        for entry_id, fields in entries:
            item = {
                (k.decode() if isinstance(k, bytes) else k): (
                    v.decode() if isinstance(v, bytes) else v
                )
                for k, v in fields.items()
            }
            item["id"] = entry_id.decode() if isinstance(entry_id, bytes) else entry_id
            items.append(item)
        next_cursor = entries[-1][0] if entries else None
        return {"items": items, "next": next_cursor}
    except Exception:
        logger.exception("Failed to fetch activity")
        return JSONResponse({"error": "unavailable"}, status_code=500)
