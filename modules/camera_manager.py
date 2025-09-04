from __future__ import annotations

import asyncio
from typing import Callable, Dict, Iterable, List

from loguru import logger

# Types for injected functions
StartFn = Callable[[dict, dict, Dict[int, object], object], object]
StopFn = Callable[[int, Dict[int, object]], None]


class CameraManager:
    """Service layer for starting and restarting camera pipelines."""

    def __init__(
        self,
        cfg: dict,
        trackers: Dict[int, object],
        redis_client,
        cams_getter: Callable[[], Iterable[dict]],
        start_fn: StartFn,
        stop_fn: StopFn,
    ) -> None:
        self.cfg = cfg
        self.trackers = trackers
        self.redis = redis_client
        self._get_cams = cams_getter
        self.start_tracker_fn = start_fn
        self.stop_tracker_fn = stop_fn

    # internal helper
    def _find_cam(self, cam_id: int) -> dict | None:
        for cam in self._get_cams():
            if cam.get("id") == cam_id:
                return cam
        return None

    async def _start_tracker_background(self, cam: dict) -> None:
        """Launch tracker start in a background thread and update status."""
        start = asyncio.get_event_loop().time()
        try:
            tr = await asyncio.to_thread(
                self.start_tracker_fn, cam, self.cfg, self.trackers, self.redis
            )
            if not tr or not getattr(tr, "online", False):
                if self.redis:
                    self.redis.hset(
                        f"camera:{cam.get('id')}:health", mapping={"status": "offline"}
                    )
                    self.redis.hset(f"camera:{cam.get('id')}", "status", "offline")
        except Exception:
            logger.exception(f"[{cam.get('id')}] tracker start failed")
            if self.redis:
                self.redis.hset(
                    f"camera:{cam.get('id')}:health", mapping={"status": "offline"}
                )
                self.redis.hset(f"camera:{cam.get('id')}", "status", "offline")
        else:
            duration = asyncio.get_event_loop().time() - start
            if duration > 5.0:
                logger.warning(f"[{cam.get('id')}] start_tracker took {duration:.2f}s")

    async def start(self, camera_id: int) -> None:
        cam = self._find_cam(camera_id)
        if not cam:
            return
        flags = {
            "enabled": cam.get("enabled", True),
            "ppe": cam.get("ppe", False),
            "vms": cam.get("visitor_mgmt", False),
            "face": cam.get("face_recognition", False),
            "counting": any(
                t in cam.get("tasks", []) for t in ("in_count", "out_count")
            ),
        }
        logger.info(
            f"[camera:{camera_id}] start type={cam.get('type')} "
            f"transport={cam.get('rtsp_transport')} flags={flags}"
        )
        asyncio.create_task(self._start_tracker_background(cam))

    async def restart(self, camera_id: int) -> None:
        cam = self._find_cam(camera_id)
        if not cam:
            return
        flags = {
            "enabled": cam.get("enabled", True),
            "ppe": cam.get("ppe", False),
            "vms": cam.get("visitor_mgmt", False),
            "face": cam.get("face_recognition", False),
            "counting": any(
                t in cam.get("tasks", []) for t in ("in_count", "out_count")
            ),
        }
        logger.info(
            f"[camera:{camera_id}] restart type={cam.get('type')} "
            f"transport={cam.get('rtsp_transport')} flags={flags}"
        )

        async def _do_restart() -> None:
            await asyncio.to_thread(self.stop_tracker_fn, camera_id, self.trackers)
            if cam.get("enabled", True) and self.cfg.get(
                "enable_person_tracking", True
            ):
                await self._start_tracker_background(cam)

        asyncio.create_task(_do_restart())

    async def refresh_flags(self, camera_id: int) -> None:
        async def _refresh() -> None:
            tr = self.trackers.get(camera_id)
            if tr:
                setattr(tr, "restart_capture", True)

        asyncio.create_task(_refresh())
