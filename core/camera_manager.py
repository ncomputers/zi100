from __future__ import annotations

"""Service for starting and restarting camera trackers."""

import asyncio
import time

from loguru import logger

from core.tracker_manager import start_tracker, stop_tracker

START_TRACKER_WARN_AFTER = 5.0


class CameraManager:
    """Manage tracker lifecycle for cameras."""

    def __init__(self, cfg: dict, trackers: dict, redis_client):
        self.cfg = cfg
        self.trackers = trackers
        self.redis = redis_client

    async def start(self, cam: dict) -> None:
        """Start tracking for ``cam`` and update Redis status."""
        start = time.perf_counter()
        cam_id = cam.get("id")
        try:
            await asyncio.to_thread(
                start_tracker, cam, self.cfg, self.trackers, self.redis
            )
            self.redis.hset(f"camera:{cam_id}", "status", "online")
        except Exception:
            logger.exception(f"[{cam_id}] tracker start failed")
            try:
                self.redis.hset(f"camera:{cam_id}", "status", "offline")
            except Exception:
                logger.exception(f"[{cam_id}] failed setting offline status")
        else:
            duration = time.perf_counter() - start
            if duration > START_TRACKER_WARN_AFTER:
                logger.warning(f"[{cam_id}] start_tracker took {duration:.2f}s")

    async def restart(self, cam: dict) -> None:
        """Restart tracker for ``cam``."""
        cam_id = cam.get("id")
        await asyncio.to_thread(stop_tracker, cam_id, self.trackers)
        await self.start(cam)

    async def refresh_flags(self, cam: dict) -> None:
        """Placeholder to refresh flags for ``cam`` without restart."""
        cam_id = cam.get("id")
        status = "online" if cam_id in self.trackers else "offline"
        self.redis.hset(f"camera:{cam_id}", "status", status)
