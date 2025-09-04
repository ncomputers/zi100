"""Application entry point orchestrating services and routers."""

from __future__ import annotations

import asyncio
import json
import os
import sys
import time
from contextlib import asynccontextmanager, suppress
from pathlib import Path
from typing import Any, Callable

from loguru import logger

import logging_config  # noqa: F401
from utils.cpu import _calc_w

# allow imports relative to this version directory without hardcoding its name
if str(Path(__file__).resolve().parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

logger = logger.bind(module="app")


def _early_cpu_setup() -> None:
    """Set thread-spawning env vars before heavy imports."""
    config_path = os.getenv("CONFIG_PATH", "config.json")
    workers_env = os.getenv("WORKERS")
    workers = None
    if workers_env:
        with suppress(ValueError):
            workers = int(workers_env)
    cores = os.cpu_count() or 1
    try:
        with open(config_path) as f:
            pct = int(json.load(f).get("cpu_limit_percent", 50))
    except (OSError, json.JSONDecodeError, ValueError, TypeError):
        pct = 50
    w = _calc_w(workers, pct, cores)
    for var in (
        "OMP_NUM_THREADS",
        "OPENBLAS_NUM_THREADS",
        "MKL_NUM_THREADS",
        "NUMEXPR_NUM_THREADS",
    ):
        os.environ[var] = str(w)
    logger.info("Resolved core count: {} of {}", w, cores)


_early_cpu_setup()

import cv2
from fastapi import FastAPI, Request
from fastapi.exception_handlers import http_exception_handler
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi_csrf_protect import CsrfProtect
from redis import Redis
from redis.exceptions import RedisError
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.sessions import SessionMiddleware

from modules.profiler import start_profiler
from utils.cpu import apply_thread_limits
from utils.gpu import configure_onnxruntime
from utils.gstreamer import probe_gstreamer
from utils.preflight import DependencyError, check_dependencies
from utils.redis import get_sync_client

try:
    from fastapi_csrf_protect import CsrfProtectMiddleware
except ImportError:  # pragma: no cover - middleware optional
    CsrfProtectMiddleware = None


# secret key loader
def _load_secret_key() -> str:
    """Fetch session secret key from config or fall back to default."""
    config_path = os.getenv("CONFIG_PATH", "config.json")
    try:
        with open(config_path) as f:
            return json.load(f).get("secret_key", "change-me")
    except (OSError, json.JSONDecodeError):
        return "change-me"


def _stop_worker(name: str, worker: object, stop_fn: Callable[[object], None]) -> None:
    """Stop a worker with standard logging and join support."""
    logger.info("Stopping {}", name)
    try:
        stop_fn(worker)
        if hasattr(worker, "join"):
            worker.join(timeout=2)
    finally:
        logger.info("{} stopped", name)


# Global exception handler for unexpected errors
async def handle_unexpected_error(request: Request, exc: Exception):
    """Catch-all handler that logs the error and resets session state."""
    if isinstance(exc, StarletteHTTPException):
        return await http_exception_handler(request, exc)

    logger.exception("Unhandled application error: {}", exc)

    session = request.scope.get("session")
    if isinstance(session, dict):
        session.clear()

    for attr in ("db", "db_session"):
        session = getattr(request.state, attr, None)
        if session and hasattr(session, "rollback"):
            with suppress(Exception):
                session.rollback()

    return JSONResponse({"detail": "Internal Server Error"}, status_code=500)


# Filter harmless connection reset errors to keep logs clean
# silent_exception_handler routine
def silent_exception_handler(loop: asyncio.AbstractEventLoop, context: dict):
    exception = context.get("exception")
    if isinstance(exception, ConnectionResetError):
        logger.warning(
            "\U0001f507 Suppressed harmless ConnectionResetError (WinError 10054)"
        )
        return
    loop.default_exception_handler(context)


from config import config as shared_config
from config import set_config
from core.config import load_branding, load_config, save_branding, save_config
from core.tracker_manager import count_log_loop, get_tracker_status, load_cameras
from modules.license import verify_license
from modules.tracker import PersonTracker
from modules.utils import SNAP_DIR
from startup import start_background_workers


def _read_initial_config(path: str) -> dict:
    """Load minimal configuration required for bootstrap."""
    logger.info("Loading config from {}", path)
    try:
        return load_config(path, None, minimal=True)
    except (OSError, json.JSONDecodeError, KeyError) as e:
        logger.exception("Failed to read config: {}", e)
        raise SystemExit(1)


def _connect_redis(url: str) -> Redis:
    """Connect to Redis and return client or exit on failure."""
    try:
        client = get_sync_client(url)
        logger.info("Connected to Redis at {}", url)
        return client
    except (RedisError, OSError) as e:
        logger.exception("Redis connection failed: {}", e)
        raise SystemExit(1)


def _apply_license(cfg: dict, license_info: dict) -> dict:
    """Integrate license information into configuration."""
    if not license_info.get("valid"):
        logger.warning("Invalid License: {}", license_info.get("error"))
        cfg["features"] = {}
    else:
        cfg["features"] = license_info.get("features", cfg.get("features", {}))
    cfg["license_info"] = license_info
    return cfg


def _load_camera_profiles(
    redis_client, cfg: dict, stream_url: str | None
) -> list[dict]:
    """Fetch camera configurations or override with CLI stream."""
    logger.info("Loading cameras")
    default_url = cfg.get("stream_url")
    if default_url is None:
        logger.warning("stream_url missing from config; defaulting to empty string")
        default_url = ""
    try:
        cams = load_cameras(redis_client, default_url)
        logger.info("Loaded {} cameras", len(cams))
        try:
            max_id = max((c.get("id", 0) for c in cams), default=0)
            cur = int(redis_client.get("camera:id_seq") or 0)
            if cur < max_id:
                redis_client.set("camera:id_seq", max_id)
        except Exception:
            logger.warning("Unable to sync camera id counter")
    except (RuntimeError, OSError) as e:
        logger.exception("Failed to load cameras: {}", e)
        raise SystemExit(1)
    if stream_url:
        cams = [
            {
                "id": 1,
                "name": "CameraCLI",
                "url": stream_url,
                "tasks": ["both"],
                "enabled": True,
            }
        ]
        logger.info("Using CLI stream URL for single camera")
    return cams


BASE_DIR = Path(__file__).parent
TEMPLATE_DIR = BASE_DIR / "templates"


# Lifespan handler consolidating startup and shutdown logic
@asynccontextmanager
async def lifespan(app: FastAPI):
    loop = asyncio.get_running_loop()
    loop.set_exception_handler(silent_exception_handler)

    config_path = os.getenv("CONFIG_PATH", "config.json")
    stream_url = os.getenv("STREAM_URL")
    workers_env = os.getenv("WORKERS")
    workers = int(workers_env) if workers_env else None

    start_time = time.time()
    cfg = init_app(config_path=config_path, stream_url=stream_url, workers=workers)

    redis_client = app.state.redis_client
    cams = app.state.cameras
    trackers: dict[int, PersonTracker] = app.state.trackers

    tasks = await start_background_workers(app, cfg, cams, trackers, redis_client)
    app.state.worker_tasks = tasks

    log_task = None
    if redis_client:
        log_task = asyncio.create_task(count_log_loop(redis_client, trackers))
    app.state.log_task = log_task

    logger.info("Starting profiler")
    try:
        start_profiler(cfg)
        logger.info("Profiler started")
    except (RuntimeError, OSError) as e:
        logger.exception("Profiler start failed: {}", e)
        raise

    elapsed = time.time() - start_time
    features = ", ".join([k for k, v in cfg.get("features", {}).items() if v]) or "none"
    logger.info("Startup complete in {:.2f}s. Enabled features: {}", elapsed, features)

    try:
        yield
    finally:
        log_task = getattr(app.state, "log_task", None)
        if log_task:
            log_task.cancel()
            with suppress(asyncio.CancelledError):
                await log_task
        await stop_all(app)


app = FastAPI(lifespan=lifespan)
app.add_middleware(SessionMiddleware, secret_key=_load_secret_key())
app.state.ready = False
app.add_exception_handler(Exception, handle_unexpected_error)

app.mount("/snapshots", StaticFiles(directory=str(SNAP_DIR)), name="snapshots")
static_mounts = [
    ("/static", "static"),
    ("/faces", "public/faces"),
    ("/invite_photos", "public/invite_photos"),
    ("/logos", "uploads/logos"),
    ("/face-api", "static/models/face-api"),
]
for route, directory_name in static_mounts:
    directory = BASE_DIR / directory_name
    if directory.is_dir():
        app.mount(route, StaticFiles(directory=str(directory)), name=directory.name)
if CsrfProtectMiddleware:
    app.add_middleware(CsrfProtectMiddleware)


@app.get("/health")
async def health() -> dict[str, str]:
    """Simple health check endpoint."""
    return {"status": "ok"}


@app.get("/health/trackers")
async def trackers_health() -> dict[int, dict]:
    """Expose status of tracker threads."""
    return get_tracker_status()


@app.get("/health/media")
async def media_health() -> dict[int, dict]:
    """Report capture backend, process status and last error for each tracker."""
    trackers: dict[int, PersonTracker] = app.state.trackers
    r = app.state.redis_client
    status = get_tracker_status()
    result: dict[int, dict] = {}
    for cam_id, tr in trackers.items():
        last_error = r.get(f"camera_debug:{cam_id}")
        result[cam_id] = {
            "backend": tr.capture_backend,
            "process_alive": status.get(cam_id, {}).get("process_alive", False),
            "last_error": last_error,
        }
    return result


# Gracefully stop background workers
async def stop_all(app: FastAPI) -> None:
    """Signal all background threads to stop and wait for termination."""
    trackers = getattr(app.state, "trackers", {})
    ppe_worker = getattr(app.state, "ppe_worker", None)
    visitor_worker = getattr(app.state, "visitor_worker", None)
    alert_worker = getattr(app.state, "alert_worker", None)
    worker_tasks = getattr(app.state, "worker_tasks", [])

    logger.info("Stopping trackers")
    for tr in trackers.values():
        tr.running = False
    from core.tracker_manager import tracker_threads

    for cam_id, info in list(tracker_threads.items()):
        for name in ("capture", "process"):
            thread = info.get(name)
            if thread:
                logger.info(f"Waiting for tracker {cam_id} {name} thread")
                thread.join(timeout=2)
                logger.info(f"Tracker {cam_id} {name} thread stopped")

    if ppe_worker:
        _stop_worker("PPE worker", ppe_worker, lambda w: setattr(w, "running", False))

    if visitor_worker:
        _stop_worker("Visitor worker", visitor_worker, lambda w: w.stop())

    if alert_worker:
        _stop_worker("Alert worker", alert_worker, lambda w: w.stop())

    logger.info("Cancelling background tasks")
    for task in worker_tasks:
        task.cancel()
    for task in worker_tasks:
        try:
            await task
            logger.info(f"Task {task.get_name() or id(task)} finished")
        except asyncio.CancelledError:
            logger.info(f"Task {task.get_name() or id(task)} cancelled")
        except (RuntimeError, OSError) as e:
            logger.exception(f"Task {task.get_name() or id(task)} error: {e}")

    from modules.profiler import stop_profiler

    stop_profiler()
    logger.info("All workers stopped")


# Routers
from routers import blueprints
from routers.health import monitor_readiness


# Initialize configuration, services, and routers
def init_app(
    config_path: str = "config.json",
    stream_url: str | None = None,
    workers: int | None = None,
) -> dict[str, Any]:
    """Configure application state and services."""
    config_path_local = (
        config_path if os.path.isabs(config_path) else str(BASE_DIR / config_path)
    )
    info = _read_initial_config(config_path_local)

    redis_url = info.get("redis_url")
    if not redis_url:
        logger.error("redis_url missing in configuration")
        raise SystemExit(1)
    temp_cfg = info["data"]
    redis_client_local: Redis = _connect_redis(redis_url)

    logger.info("Loading full configuration")
    try:
        cfg: dict[str, Any] = load_config(
            config_path_local, redis_client_local, data=temp_cfg
        )
    except (OSError, json.JSONDecodeError, RuntimeError) as e:
        logger.exception("Configuration load failed: {}", e)
        raise SystemExit(1)
    cfg["secret_key"] = os.getenv("CSRF_SECRET_KEY", cfg.get("secret_key", ""))

    logging_config.set_log_level(cfg.get("log_level", logging_config.LOG_LEVEL))
    probe_gstreamer(cfg)

    branding_path = str(Path(config_path_local).with_name("branding.json"))
    cfg["branding"] = load_branding(branding_path)
    license_info = verify_license(cfg.get("license_key", ""))
    cfg = _apply_license(cfg, license_info)
    if not license_info.get("valid"):
        save_config(cfg, config_path_local, redis_client_local)
    redis_client_local.set("license_info", json.dumps(license_info))

    try:
        check_dependencies(cfg, BASE_DIR)
    except DependencyError as e:
        logger.error(str(e))
        raise SystemExit(1)

    configure_onnxruntime(cfg)

    from modules.ffmpeg_stream import _supports_drop

    cfg["ffmpeg_supports_drop"] = _supports_drop()
    set_config(cfg)

    cams = _load_camera_profiles(redis_client_local, cfg, stream_url)

    trackers: dict[int, PersonTracker] = {}

    app.state.config = cfg
    app.state.config_path = config_path_local
    app.state.redis_client = redis_client_local
    app.state.cameras = cams
    app.state.trackers = trackers
    app.state.ppe_worker = None
    app.state.visitor_worker = None
    app.state.alert_worker = None
    app.state.branding_path = branding_path
    app.state.templates = Jinja2Templates(directory=str(TEMPLATE_DIR))

    monitor_readiness(app)

    blueprints.init_all(
        cfg,
        trackers,
        cams,
        redis_client_local,
        str(TEMPLATE_DIR),
        config_path_local,
        branding_path,
    )
    blueprints.register_blueprints(app)
    apply_thread_limits(cfg, workers)

    return cfg


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app:app",
        host="0.0.0.0",
        port=int(shared_config.get("port", 8000)),
    )
