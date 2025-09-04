"""Manage PersonTracker instances and related counters."""

from __future__ import annotations

import asyncio
import json
import threading
import time
from datetime import date
from typing import Dict, List

import psutil
import redis
from loguru import logger
from redis.exceptions import RedisError

from modules import camera_factory
from modules.tracker import PersonTracker
from utils.redis import trim_sorted_set_sync

from .config import COUNT_GROUPS, PPE_TASKS, load_config, save_config

lock = threading.Lock()

# store tracker threads and restart metadata
tracker_threads: Dict[int, dict] = {}

# base delay for exponential backoff (seconds)
BACKOFF_BASE = 1


# Normalize raw task configuration into a list of task identifiers
def normalize_tasks(tasks) -> List[str]:
    """Return list of task names from raw task structure.

    The input can be ``None``, a list of task names, or a legacy
    dictionary describing task groups. Missing or invalid values
    default to ``["in_count", "out_count"]``.
    """

    if isinstance(tasks, dict):
        lst: List[str] = []
        if "counting" in tasks:
            if "in" in tasks["counting"]:
                lst.append("in_count")
            if "out" in tasks["counting"]:
                lst.append("out_count")
        lst.extend(tasks.get("ppe", []))
        if tasks.get("full_monitor"):
            lst.append("full_monitor")
        tasks = lst
    if not isinstance(tasks, list):
        return ["in_count", "out_count"]
    return tasks


# load_cameras routine
def load_cameras(r: redis.Redis, default_url: str) -> List[dict]:
    data = r.get("cameras") if hasattr(r, "get") else r.hget("cameras", "data")
    if data:
        try:
            cams = json.loads(data)
            changed = False
            for cam in cams:
                cam["tasks"] = normalize_tasks(cam.get("tasks"))
                cam.pop("mode", None)
                cam.setdefault("type", "http")
                cam.setdefault("reverse", False)
                cam.setdefault("line_orientation", "vertical")
                cam.setdefault("orientation", "vertical")
                cam.setdefault("resolution", "original")
                if "show" not in cam:
                    cam["show"] = True
                    changed = True
                cam.setdefault("archived", False)
            if changed:
                save_cameras(cams, r)
            return cams
        except json.JSONDecodeError:
            logger.error("Invalid cameras data in Redis, resetting")
    # no cameras configured; return empty list so user can add manually
    data = json.dumps([])
    if hasattr(r, "set"):
        r.set("cameras", data)
    else:
        r.hset("cameras", "data", data)
    return []


# save_cameras routine
def save_cameras(cams: List[dict], r: redis.Redis) -> None:
    data = json.dumps(cams)
    if hasattr(r, "set"):
        r.set("cameras", data)
    else:
        r.hset("cameras", "data", data)


def _apply_overrides(cam: dict, redis_client: redis.Redis) -> dict:
    """Apply per-camera overrides stored in Redis."""
    override_key = f"camera:{cam.get('id')}"
    try:
        data = redis_client.get(override_key)
        if data:
            try:
                overrides = json.loads(data)
            except json.JSONDecodeError:
                overrides = {}
            for k in ["url", "backend", "ffmpeg_flags", "pipeline", "profile"]:
                if k in overrides and overrides[k] is not None:
                    cam[k] = overrides[k]
    except RedisError:
        pass
    return cam


def _check_license(
    cfg: dict, tasks: List[str], trackers: Dict[int, PersonTracker]
) -> List[str] | None:
    """Return filtered tasks if license permits, otherwise ``None``."""
    lic = cfg.get("license_info", {})
    if lic:
        max_cams = lic.get("max_cameras")
        if max_cams is not None and len(trackers) >= max_cams:
            logger.warning("Camera limit reached, not starting tracker")
            return None
        features = lic.get("features", {})
        count_tasks = {"in_count", "out_count"}
        if not features.get("in_out_counting", True):
            tasks = [t for t in tasks if t not in count_tasks]
        if not features.get("ppe_detection", True):
            tasks = [t for t in tasks if t not in PPE_TASKS]
        if not tasks:
            logger.warning("No licensed tasks for this camera")
            return None
    return tasks


def _spawn_threads(tracker: PersonTracker) -> Dict[str, threading.Thread]:
    """Create and start worker threads for a tracker."""
    cap_thread = threading.Thread(target=tracker.capture_worker.run, daemon=True)
    inf_thread = threading.Thread(target=tracker.infer_worker.run, daemon=True)
    post_thread = threading.Thread(target=tracker.post_worker.run, daemon=True)
    cap_thread.start()
    inf_thread.start()
    post_thread.start()
    return {"capture": cap_thread, "infer": inf_thread, "post": post_thread}


def _broadcast(trackers: Dict[int, PersonTracker], r: redis.Redis) -> None:
    from .stats import broadcast_stats

    broadcast_stats(trackers, r)


# start_tracker routine
def start_tracker(
    cam: dict, cfg: dict, trackers: Dict[int, PersonTracker], r: redis.Redis
) -> PersonTracker | None:
    if not cfg.get("enable_person_tracking", True):
        logger.info("Person tracking disabled, not starting tracker")
        return None

    cam = _apply_overrides(cam, r)

    tasks = normalize_tasks(cam.get("tasks"))
    tasks = _check_license(cfg, tasks, trackers)
    if tasks is None:
        return None

    required_tasks = {"in_count", "out_count", "full_monitor"} | set(PPE_TASKS)
    if not set(tasks) & required_tasks:
        logger.info("No counting/PPE tasks for this camera; tracker not started")
        return None

    camera_factory.redis_client = r
    cfg_cam = dict(cfg)
    if cam.get("backend"):
        cfg_cam["backend_priority"] = cam["backend"]
    if cam.get("ffmpeg_flags") is not None:
        cfg_cam["ffmpeg_flags"] = cam["ffmpeg_flags"]
    if cam.get("pipeline"):
        cfg_cam["pipeline"] = cam["pipeline"]
    if cam.get("profile"):
        cfg_cam["profile"] = cam["profile"]
    tr = PersonTracker(
        cam["id"],
        cam["url"],
        cfg_cam.get("object_classes", ["person"]),
        cfg_cam,
        tasks,
        cam.get("type", "http"),
        line_orientation=cam.get("line_orientation", "vertical"),
        reverse=cam.get("reverse", False),
        resolution=cam.get("resolution", "original"),
        rtsp_transport=cam.get("rtsp_transport", "tcp"),
        update_callback=lambda: _broadcast(trackers, r),
    )
    trackers[cam["id"]] = tr
    threads = _spawn_threads(tr)
    with lock:
        tracker_threads[cam["id"]] = {
            **threads,
            "restart_attempts": 0,
            "timer": None,
        }
    return tr


# stop_tracker routine
def stop_tracker(cam_id: int, trackers: Dict[int, PersonTracker]) -> None:
    tr = trackers.pop(cam_id, None)
    if tr:
        tr.running = False
    with lock:
        info = tracker_threads.pop(cam_id, None)
    if info and info.get("timer"):
        info["timer"].cancel()


# reset_counts routine
def reset_counts(trackers: Dict[int, PersonTracker]) -> None:
    for tr in trackers.values():
        tr.in_count = 0
        tr.out_count = 0
        tr.tracks.clear()
        tr.prev_date = date.today()
        tr.redis.mset(
            {tr.key_in: 0, tr.key_out: 0, tr.key_date: tr.prev_date.isoformat()}
        )
    logger.info("Counts reset")


# log_counts routine
def log_counts(r: redis.Redis, trackers: Dict[int, PersonTracker]) -> None:
    ts = int(time.time())
    data = {"ts": ts}
    for g in COUNT_GROUPS.keys():
        in_c = sum(t.in_counts.get(g, 0) for t in trackers.values())
        out_c = sum(t.out_counts.get(g, 0) for t in trackers.values())
        data[f"in_{g}"] = in_c
        data[f"out_{g}"] = out_c
    entry = json.dumps(data)
    r.zadd("history", {entry: ts})
    trim_sorted_set_sync(r, "history", ts)
    r.zremrangebyrank("history", 0, -10001)
    from .stats import broadcast_stats

    broadcast_stats(trackers, r)


async def count_log_loop(r: redis.Redis, trackers: Dict[int, PersonTracker]):
    while True:
        log_counts(r, trackers)
        await asyncio.sleep(60)


def _restart_threads(cam_id: int, tr: PersonTracker) -> None:
    """Restart capture, inference and post-process threads for a tracker."""
    last_error = getattr(tr, "stream_error", "")
    qsize = None
    if hasattr(tr, "frame_queue"):
        try:
            qsize = tr.frame_queue.qsize()
        except (NotImplementedError, RuntimeError):
            qsize = None
    mem = psutil.Process().memory_info().rss / (1024**2)
    logger.info(
        f"Tracker {cam_id} restart requested; last_error={last_error}, queue={qsize}, mem={mem:.1f}MB"
    )

    cap_target = getattr(tr, "capture_loop", lambda: None)
    inf_target = getattr(tr, "infer_loop", getattr(tr, "process_loop", lambda: None))
    post_target = getattr(tr, "post_process_loop", lambda: None)
    cap = threading.Thread(target=cap_target, daemon=True)
    inf = threading.Thread(target=inf_target, daemon=True)
    post = threading.Thread(target=post_target, daemon=True)
    cap.start()
    inf.start()
    post.start()
    with lock:
        tracker_threads[cam_id]["capture"] = cap
        tracker_threads[cam_id]["infer"] = inf
        tracker_threads[cam_id]["post"] = post
        if "process" in tracker_threads[cam_id]:
            tracker_threads[cam_id]["process"] = inf


def reset_backoff(cam_id: int) -> None:
    """Reset restart attempts and cancel any pending restart timer."""
    with lock:
        info = tracker_threads.get(cam_id)
    if not info:
        return
    timer = info.get("timer")
    if timer and timer.is_alive():
        timer.cancel()
        info["timer"] = None
    info["restart_attempts"] = 0


def watchdog_tick(trackers: Dict[int, PersonTracker]) -> None:
    """Check tracker threads and restart if needed."""
    with lock:
        items = list(tracker_threads.items())
    for cam_id, info in items:
        tr = trackers.get(cam_id)
        if not tr:
            continue
        cap_alive = info["capture"].is_alive()
        inf_thread = info.get("infer") or info.get("process")
        post_thread = info.get("post")
        inf_alive = inf_thread.is_alive() if inf_thread else True
        post_alive = post_thread.is_alive() if post_thread else True
        if cap_alive and inf_alive and post_alive:
            if info.get("restart_attempts"):
                logger.info(
                    f"Tracker {cam_id} back online after {info['restart_attempts']} attempts"
                )
            reset_backoff(cam_id)
            continue
        timer = info.get("timer")
        if timer and timer.is_alive():
            continue
        attempt = info.get("restart_attempts", 0) + 1
        delay = min(60, BACKOFF_BASE * (2 ** (attempt - 1)))
        last_error = getattr(tr, "stream_error", "")
        qsize = None
        if hasattr(tr, "frame_queue"):
            try:
                qsize = tr.frame_queue.qsize()
            except (NotImplementedError, RuntimeError):
                qsize = None
        mem = psutil.Process().memory_info().rss / (1024**2)
        logger.warning(
            f"Tracker {cam_id} thread stopped. Restarting in {delay}s (attempt {attempt}). "
            f"last_error={last_error}, queue={qsize}, mem={mem:.1f}MB"
        )
        info["restart_attempts"] = attempt

        def _do_restart():
            logger.info(f"Restarting tracker {cam_id} (attempt {attempt})")
            tr.running = True
            _restart_threads(cam_id, tr)

        timer = threading.Timer(delay, _do_restart)
        info["timer"] = timer
        timer.start()


def watchdog_loop(trackers: Dict[int, PersonTracker]) -> None:
    """Background watchdog loop."""
    while True:
        watchdog_tick(trackers)
        time.sleep(1)


def start_watchdog(trackers: Dict[int, PersonTracker]) -> None:
    """Launch watchdog monitoring thread."""
    threading.Thread(target=watchdog_loop, args=(trackers,), daemon=True).start()


def get_tracker_status() -> Dict[int, dict]:
    """Return current status of tracker threads."""
    status: Dict[int, dict] = {}
    with lock:
        items = list(tracker_threads.items())
    for cam_id, info in items:
        inf_thread = info.get("infer") or info.get("process")
        post_thread = info.get("post")
        entry = {
            "capture_alive": info["capture"].is_alive(),
            "restart_attempts": info.get("restart_attempts", 0),
        }
        if inf_thread:
            alive = inf_thread.is_alive()
            entry["infer_alive"] = alive
            if "process" in info:
                entry["process_alive"] = alive
        if post_thread:
            entry["post_alive"] = post_thread.is_alive()
        status[cam_id] = entry
    return status


last_status: str | None = None


# handle_status_change routine
def handle_status_change(status: str, r: redis.Redis) -> None:
    global last_status
    if status == last_status:
        return
    last_status = status
    ts = int(time.time())
    if status == "yellow":
        r.incr("yellow_alert_count")
        entry = {
            "ts": ts,
            "cam_id": 0,
            "track_id": 0,
            "status": "yellow_alert",
            "conf": 0,
            "color": None,
            "path": None,
        }
        r.zadd("ppe_logs", {json.dumps(entry): ts})
        r.incr("ppe_report_version")
        cfg_data = r.get("config")
        limit = 1000
        retention_secs = 7 * 24 * 60 * 60
        if cfg_data:
            try:
                cfg = json.loads(cfg_data)
                limit = cfg.get("ppe_log_limit", 1000)
                retention_secs = int(cfg.get("ppe_log_retention_secs", retention_secs))
            except (json.JSONDecodeError, ValueError, TypeError):
                pass
        trim_sorted_set_sync(r, "ppe_logs", ts, retention_secs)
        r.zremrangebyrank("ppe_logs", 0, -limit - 1)
    elif status == "red":
        r.incr("red_alert_count")
        entry = {
            "ts": ts,
            "cam_id": 0,
            "track_id": 0,
            "status": "red_alert",
            "conf": 0,
            "color": None,
            "path": None,
        }
        r.zadd("ppe_logs", {json.dumps(entry): ts})
        r.incr("ppe_report_version")
        cfg_data = r.get("config")
        limit = 1000
        retention_secs = 7 * 24 * 60 * 60
        if cfg_data:
            try:
                cfg = json.loads(cfg_data)
                limit = cfg.get("ppe_log_limit", 1000)
                retention_secs = int(cfg.get("ppe_log_retention_secs", retention_secs))
            except (json.JSONDecodeError, ValueError, TypeError):
                pass
        trim_sorted_set_sync(r, "ppe_logs", ts, retention_secs)
        r.zremrangebyrank("ppe_logs", 0, -limit - 1)
