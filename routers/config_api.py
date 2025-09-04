"""Expose runtime configuration details."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from utils.deps import get_settings

router = APIRouter()


@router.get("/config")
async def config_endpoint(cfg: dict = Depends(get_settings)) -> dict:
    """Return selected configuration flags for client use."""
    return {"ffmpeg_supports_drop": cfg.get("ffmpeg_supports_drop", False)}
