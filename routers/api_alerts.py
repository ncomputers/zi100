"""API endpoints for recent alert data."""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse
from loguru import logger

from utils.deps import get_redis

router = APIRouter()

ALERTS_KEY = "alerts:recent"


@router.get("/api/alerts/recent")
async def get_recent_alerts(
    limit: int = Query(20, ge=1, le=100),
    redis=Depends(get_redis),
):
    """Return a list of recent alert messages."""
    try:
        raw = redis.lrange(ALERTS_KEY, -limit, -1) if redis else []
        alerts: list = []
        for item in raw:
            if isinstance(item, (bytes, bytearray)):
                item = item.decode()
            try:
                alerts.append(json.loads(item))
            except Exception:
                alerts.append(item)
        return alerts
    except Exception:
        logger.exception("Failed to fetch alerts")
        return JSONResponse({"error": "unavailable"}, status_code=500)
