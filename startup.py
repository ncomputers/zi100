import asyncio
import time
from pathlib import Path
from typing import Any, Awaitable, Callable

from fastapi import FastAPI
from loguru import logger
from redis import Redis

from core.tracker_manager import start_tracker, start_watchdog
from modules.alerts import AlertWorker
from modules.model_registry import get_insightface, get_yolo
from modules.ppe_worker import PPEDetector
from modules.tracker import PersonTracker
from modules.utils import SNAP_DIR
from utils.gpu import get_device

BASE_DIR = Path(__file__).parent


async def start_worker(name: str, coro: Callable[[], Awaitable[None]]) -> None:
    """Run a worker coroutine with standard logging and error handling."""
    logger.info("Starting {}", name)
    try:
        await coro()
        logger.info("{} started", name)
    except (RuntimeError, OSError) as e:
        logger.exception("{} initialization failed: {}", name, e)
        raise
    finally:
        logger.info("{} stopped", name)


async def preload_models(cfg: dict[str, Any]) -> None:
    """Preload heavy models into the shared registry."""
    device = get_device(device=cfg.get("device"))

    async def _load(fn: Callable[[], Any], note: str) -> None:
        start = time.perf_counter()
        await asyncio.to_thread(fn)
        logger.info("{} loaded in {:.2f}s", note, time.perf_counter() - start)

    tasks = []
    person_model = cfg.get("person_model")
    if person_model:
        tasks.append(_load(lambda: get_yolo(person_model, device), f"{person_model}"))
    plate_model = cfg.get("plate_model", "license_plate_detector.pt")
    tasks.append(_load(lambda: get_yolo(plate_model, device), f"{plate_model}"))
    if cfg.get("features", {}).get("visitor_mgmt"):
        visitor_model = cfg.get("visitor_model", "buffalo_l")
        tasks.append(_load(lambda: get_insightface(visitor_model), f"{visitor_model}"))
    if tasks:
        await asyncio.gather(*tasks)


async def init_trackers(
    cams: list[dict[str, Any]],
    cfg: dict[str, Any],
    trackers: dict[int, PersonTracker],
    redis_client: Redis,
) -> None:
    """Initialize trackers for enabled cameras using the given Redis client."""
    enabled = [cam for cam in cams if cam.get("enabled", True)]
    logger.info("Initializing trackers for {} cameras", len(enabled))
    try:

        async def _start(cam: dict[str, Any]) -> None:
            await asyncio.to_thread(start_tracker, cam, cfg, trackers, redis_client)

        await asyncio.gather(*(_start(cam) for cam in enabled))
        await asyncio.to_thread(start_watchdog, trackers)
        logger.info("Trackers initialized")
    except (RuntimeError, OSError) as e:
        logger.exception("Tracker initialization failed: {}", e)
        raise


async def alert_worker(app: FastAPI, cfg: dict[str, Any], redis_client: Redis) -> None:
    """Launch the alert worker using the provided Redis client."""
    app.state.alert_worker = AlertWorker(cfg, redis_client, BASE_DIR)


async def ppe_worker(
    app: FastAPI,
    cfg: dict[str, Any],
    trackers: dict[int, PersonTracker],
    redis_client: Redis,
) -> None:
    """Launch the PPE detection worker if enabled and supported."""
    if cfg.get("features", {}).get("ppe_detection"):
        device = get_device()
        if getattr(device, "type", "") == "cuda":
            from core.stats import broadcast_stats

            worker = PPEDetector(
                cfg,
                redis_client,
                SNAP_DIR,
                lambda: broadcast_stats(trackers, redis_client),
            )
            worker.start()
            app.state.ppe_worker = worker
        else:
            logger.warning("CUDA device not available, disabling PPE detection")
            cfg.setdefault("features", {})["ppe_detection"] = False


async def visitor_worker(
    app: FastAPI, cfg: dict[str, Any], redis_client: Redis
) -> None:
    """Launch the visitor worker using the provided Redis client."""
    from workers.visitor import VisitorWorker

    worker = VisitorWorker(cfg, redis_client)
    worker.start()
    if worker.running:
        app.state.visitor_worker = worker
    else:
        app.state.visitor_worker = None
        logger.warning("Visitor worker not running; disabling")


async def start_background_workers(
    app: FastAPI,
    cfg: dict[str, Any],
    cams: list[dict[str, Any]],
    trackers: dict[int, PersonTracker],
    redis_client: Redis,
) -> list[asyncio.Task[None]]:
    """Preload models and create background tasks."""
    await preload_models(cfg)
    worker_defs = [
        ("alert-worker", lambda: alert_worker(app, cfg, redis_client)),
        ("ppe-detector", lambda: ppe_worker(app, cfg, trackers, redis_client)),
        ("visitor-worker", lambda: visitor_worker(app, cfg, redis_client)),
    ]

    tasks = [
        asyncio.create_task(
            init_trackers(cams, cfg, trackers, redis_client),
            name="tracker-initialization",
        )
    ]
    tasks.extend(
        asyncio.create_task(start_worker(name, worker), name=name)
        for name, worker in worker_defs
    )
    return tasks
