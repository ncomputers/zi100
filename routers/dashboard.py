"""Dashboard and stats routes."""

from __future__ import annotations

import asyncio
import inspect
import io
import json
import os
import queue
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Annotated, AsyncIterator, Dict, Iterable

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import (
    HTMLResponse,
    JSONResponse,
    RedirectResponse,
    StreamingResponse,
)
from fastapi.templating import Jinja2Templates
from loguru import logger
from mjpeg.server import MJPEGResponse
from PIL import Image
from redis.exceptions import ConnectionError as RedisConnectionError

from core.config import ANOMALY_ITEMS, PPE_TASKS
from modules.gstreamer_stream import _ensure_gst
from modules.utils import require_roles
from utils.async_utils import run_with_timeout
from utils.deps import get_cameras, get_redis, get_settings, get_templates, get_trackers
from utils.time import parse_range

router = APIRouter()

logger = logger.bind(module="dashboard")


async def fetch_stats(
    redis, start_ts: int, end_ts: int
) -> tuple[list[int], list[int], list[int], list[int], list[int], dict[str, int]]:
    """Retrieve cumulative stats from Redis."""
    try:
        totals = redis.hgetall("stats_totals")
        if inspect.isawaitable(totals):
            totals = await totals
    except Exception:
        totals = {}

    if not totals:
        try:
            entries = redis.xrevrange("stats_stream", count=1)
            if inspect.isawaitable(entries):
                entries = await entries
            if entries:
                _id, fields = entries[0]
                raw = fields.get(b"data") or fields.get("data")
                if raw:
                    totals = json.loads(
                        raw.decode() if isinstance(raw, (bytes, bytearray)) else raw
                    )
        except Exception:
            totals = {}
    else:
        totals = {
            (k.decode() if isinstance(k, (bytes, bytearray)) else k): (
                v.decode() if isinstance(v, (bytes, bytearray)) else v
            )
            for k, v in totals.items()
        }
        totals = {
            **totals,
            "in_count": int(totals.get("in_count", 0)),
            "out_count": int(totals.get("out_count", 0)),
            "current": int(totals.get("current", 0)),
            "anomaly_counts": json.loads(totals.get("anomaly_counts", "{}")),
            "group_counts": json.loads(totals.get("group_counts", "{}")),
        }

    timeline = [end_ts]
    in_counts = [totals.get("in_count", 0)]
    out_counts = [totals.get("out_count", 0)]
    current_vals = [totals.get("current", 0)]
    vehicle_counts = [
        (totals.get("group_counts", {}).get("vehicle", {}) or {}).get("current", 0)
    ]
    anomaly_totals: dict[str, int] = totals.get("anomaly_counts", {}) or {}
    return (
        timeline,
        in_counts,
        out_counts,
        vehicle_counts,
        current_vals,
        anomaly_totals,
    )


def aggregate_metrics(
    data: tuple[list[int], list[int], list[int], list[int], list[int], dict[str, int]],
) -> dict:
    """Compute aggregates from raw timeline data."""
    (
        timeline,
        in_counts,
        out_counts,
        vehicle_counts,
        current_vals,
        anomaly_totals,
    ) = data
    current_val = current_vals[-1] if current_vals else 0
    return {
        "timeline": timeline,
        "in_counts": in_counts,
        "out_counts": out_counts,
        "vehicle_counts": vehicle_counts,
        "anomaly_counts": anomaly_totals,
        "current": current_val,
        "current_occupancy": current_val,
        "vehicles_detected": sum(vehicle_counts),
        "safety_violations": sum(anomaly_totals.values()),
    }


def compute_group_counts(
    trackers_map: Dict[int, "PersonTracker"], groups: Iterable[str]
) -> dict[str, dict[str, int]]:
    """Aggregate per-group in/out/current counts across trackers."""

    group_counts: dict[str, dict[str, int]] = {}
    for g in groups:
        in_g = sum(getattr(t, "in_counts", {}).get(g, 0) for t in trackers_map.values())
        out_g = sum(
            getattr(t, "out_counts", {}).get(g, 0) for t in trackers_map.values()
        )
        group_counts[g] = {"in": in_g, "out": out_g, "current": in_g - out_g}
    return group_counts


@router.get("/")
async def index(
    request: Request,
    cfg: dict = Depends(get_settings),
    trackers_map: Dict[int, "PersonTracker"] = Depends(get_trackers),
    cams: list = Depends(get_cameras),
    redis=Depends(get_redis),
    templates: Jinja2Templates = Depends(get_templates),
):
    res = require_roles(request, ["admin", "viewer"])
    if isinstance(res, RedirectResponse):
        return res
    error_message = request.query_params.get("error")
    groups = cfg.get("track_objects", ["person"])
    group_counts = compute_group_counts(trackers_map, groups)
    current = group_counts.get("person", {"current": 0})["current"]
    in_c = group_counts.get("person", {"in": 0})["in"]
    out_c = group_counts.get("person", {"out": 0})["out"]
    max_cap = cfg["max_capacity"]
    warn_lim = max_cap * cfg["warn_threshold"] / 100
    status = "green" if current < warn_lim else "yellow" if current < max_cap else "red"
    active = [c for c in cams if c.get("show", False)]
    count_keys = [f"{item}_count" for item in ANOMALY_ITEMS]
    try:
        count_vals = await run_with_timeout(redis.mget, count_keys, timeout=5)
    except asyncio.TimeoutError:
        logger.error("Timed out fetching anomaly counts from Redis")
        return RedirectResponse(
            "/dashboard?error=Unable%20to%20load%20stats", status_code=303
        )
    anomaly_counts = {
        item: int(val or 0) for item, val in zip(ANOMALY_ITEMS, count_vals)
    }
    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "max_capacity": max_cap,
            "status": status,
            "current": current,
            "cameras": active,
            "cfg": cfg,
            "anomaly_counts": anomaly_counts,
            "group_counts": group_counts,
            "error_message": error_message,
        },
    )


@router.get("/debug")
async def debug_page(
    request: Request,
    cfg: dict = Depends(get_settings),
    templates: Jinja2Templates = Depends(get_templates),
):
    res = require_roles(request, ["admin", "viewer"])
    if isinstance(res, RedirectResponse):
        return res
    gst_available = _ensure_gst()
    return templates.TemplateResponse(
        "debug_stats.html",
        {"request": request, "cfg": cfg, "gst_available": gst_available},
    )


@router.get("/debug/camera")
async def debug_camera_page(
    request: Request,
    trackers_map: Dict[int, "PersonTracker"] = Depends(get_trackers),
    cams: list = Depends(get_cameras),
    redis=Depends(get_redis),
    templates: Jinja2Templates = Depends(get_templates),
):
    res = require_roles(request, ["admin"])
    if isinstance(res, RedirectResponse):
        return res
    cam_info = []
    for cam in cams:
        cid = cam.get("id")
        tr = trackers_map.get(cid)
        try:
            if asyncio.iscoroutinefunction(redis.get):
                raw = await redis.get(f"camera_debug:{cid}") or ""
            else:
                raw = await asyncio.to_thread(redis.get, f"camera_debug:{cid}") or ""
        except Exception:
            user = request.session.get("user", {}).get("name")
            logger.bind(user=user, cam_id=cid).exception(
                "Failed to fetch camera debug info"
            )
            raw = ""
        debug = raw.decode() if isinstance(raw, (bytes, bytearray)) else raw
        attempts = []
        summary = ""
        runtime = []
        if debug:
            try:
                data = json.loads(debug)
                if isinstance(data, dict) and "attempts" in data:
                    for att in data.get("attempts", []):
                        attempts.append(
                            {
                                "backend": att.get("backend", ""),
                                "command": att.get("command")
                                or att.get("pipeline", ""),
                                "error": att.get("error", ""),
                            }
                        )
                    summary = data.get("summary") or data.get("final", "")
                    for ev in data.get("runtime", []):
                        ts = ev.get("ts")
                        ev_ts = (
                            datetime.fromtimestamp(ts).isoformat()
                            if isinstance(ts, (int, float))
                            else ""
                        )
                        runtime.append(
                            {
                                "ts": ev_ts,
                                "backend": ev.get("backend", ""),
                                "message": ev.get("message", ""),
                            }
                        )
                else:
                    summary = debug
            except Exception:
                summary = debug
        stats = tr.get_debug_stats() if tr and hasattr(tr, "get_debug_stats") else {}
        if stats.get("last_capture_ts"):
            stats["last_capture_ts"] = datetime.fromtimestamp(
                stats["last_capture_ts"]
            ).isoformat()
        if stats.get("last_process_ts"):
            stats["last_process_ts"] = datetime.fromtimestamp(
                stats["last_process_ts"]
            ).isoformat()
        restart_ts = getattr(tr, "debug_restart_ts", None)
        restart_str = (
            datetime.fromtimestamp(restart_ts).isoformat() if restart_ts else None
        )
        pipeline = getattr(tr, "pipeline_info", "") or ""
        if not pipeline:
            if attempts:
                pipeline = attempts[-1].get("command", "")
            else:
                # Provide a reasonable FFmpeg placeholder when no attempts exist
                pipeline = (
                    "ffmpeg -rtsp_transport tcp -i {url} -f rawvideo -pix_fmt bgr24 -"
                )
        info = {
            "id": cid,
            "name": cam.get("name", f"Camera {cid}"),
            "pipeline": pipeline,
            "backend": getattr(tr, "capture_backend", ""),
            "restart_ts": restart_str,
            "debug_attempts": attempts,
            "debug_summary": summary,
            "debug_runtime": runtime,
            "flags": json.dumps(
                {
                    "url": getattr(tr, "src", ""),
                    "type": getattr(tr, "src_type", ""),
                    "resolution": getattr(tr, "resolution", ""),
                    "rtsp_transport": getattr(tr, "rtsp_transport", ""),
                    "stream_mode": getattr(tr, "stream_mode", ""),
                    "ffmpeg_flags": getattr(tr, "cfg", {}).get("ffmpeg_flags", ""),
                },
                indent=2,
            ),
            "stats": stats,
            "rtsp_transport": getattr(tr, "rtsp_transport", ""),
            "ffmpeg_flags": getattr(tr, "cfg", {}).get("ffmpeg_flags", ""),
        }
        cam_info.append(info)
    accept = getattr(request, "headers", {}).get("accept", "")
    if "application/json" in accept:
        return JSONResponse(cam_info)

    return templates.TemplateResponse(
        "debug_camera.html",
        {"request": request, "cameras": cam_info},
    )


@router.post("/debug/camera")
async def debug_camera_update(
    request: Request,
    trackers_map: Dict[int, "PersonTracker"] = Depends(get_trackers),
    redis=Depends(get_redis),
):
    res = require_roles(request, ["admin"])
    if isinstance(res, RedirectResponse):
        return res
    data = await request.json()
    cam_id_raw = data.get("cam_id")
    if cam_id_raw is None:
        return JSONResponse({"error": "cam_id required"}, status_code=400)
    try:
        cam_id = int(cam_id_raw)
    except ValueError:
        return JSONResponse({"error": "cam_id must be integer"}, status_code=400)
    tr = trackers_map.get(cam_id)
    if not tr:
        return JSONResponse({"error": "Not found"}, status_code=404)
    params = {k: v for k, v in data.items() if k != "cam_id"}
    flags = params.pop("flags", None)
    pipeline = params.pop("pipeline", None)
    if isinstance(flags, str):
        try:
            params.update(json.loads(flags))
        except json.JSONDecodeError:
            pass
    tr.apply_debug_pipeline(pipeline=pipeline, **params)
    updates = {
        k: v
        for k, v in params.items()
        if k in {"rtsp_transport", "ffmpeg_flags", "url", "backend"}
    }
    if pipeline is not None:
        updates["pipeline"] = pipeline
    if updates:
        try:
            await asyncio.to_thread(redis.hset, f"camera:{cam_id}", mapping=updates)
        except Exception:
            logger.exception("Failed to update camera overrides in Redis")
    tr.restart_capture = True
    command = " ".join((tr.pipeline_info or "").split())
    return {
        "cam_id": cam_id,
        "pipeline": tr.pipeline_info,
        "backend": tr.capture_backend,
        "command": command,
        "restart_ts": getattr(tr, "debug_restart_ts", None),
        "restarting": True,
    }


async def _stream_response(
    cam_id: int,
    request: Request,
    trackers_map: Dict[int, "PersonTracker"],
    *,
    raw: bool = False,
):
    res = require_roles(request, ["admin", "viewer"])
    if isinstance(res, RedirectResponse):
        return res
    tr = trackers_map.get(cam_id)
    if not tr:
        # Attempt to start the tracker if the camera exists
        from routers.cameras import camera_manager

        cam = getattr(camera_manager, "_find_cam", lambda _cid: None)(cam_id)
        if not cam:
            return HTMLResponse("Not found", status_code=404)

        await camera_manager.start(cam_id)

        for _ in range(10):
            tr = trackers_map.get(cam_id)
            if tr and getattr(tr, "output_frame", None) is not None:
                break
            await asyncio.sleep(0.1)

        if not tr:
            return HTMLResponse("Not found", status_code=404)
        if getattr(tr, "output_frame", None) is None:
            return HTMLResponse("Camera starting, retry shortly.", status_code=503)

    def gen():
        if not raw:
            tr.viewers += 1
            if tr.viewers == 1:
                tr.restart_capture = True
        no_frame_logged = False
        try:
            while True:
                frame = tr.raw_frame if raw else tr.output_frame
                if frame is None:
                    if not no_frame_logged:
                        logger.warning(
                            f"[{cam_id}] No frame for {'clean' if raw else 'preview'}"
                        )
                        no_frame_logged = True
                    time.sleep(0.1)
                    continue
                if no_frame_logged:
                    logger.info(
                        f"[{cam_id}] Resumed frames for {'clean' if raw else 'preview'}"
                    )
                    no_frame_logged = False
                if raw and hasattr(frame, "download"):
                    frame = frame.download()
                img = Image.fromarray(frame[:, :, ::-1])
                buf = io.BytesIO()
                img.save(buf, format="JPEG")
                yield buf.getvalue()
                if not raw:
                    time.sleep(1 / tr.fps)
        finally:
            if not raw:
                tr.viewers -= 1
                if tr.viewers == 0:
                    tr.restart_capture = True

    resp = MJPEGResponse(gen())
    resp.headers["Access-Control-Allow-Origin"] = "*"
    return resp


@router.get("/stream/preview/{cam_id}")
async def stream_preview(
    cam_id: int,
    request: Request,
    trackers_map: Dict[int, "PersonTracker"] = Depends(get_trackers),
):
    return await _stream_response(cam_id, request, trackers_map)


@router.get("/stream/clean/{cam_id}")
async def stream_clean(
    cam_id: int,
    request: Request,
    trackers_map: Dict[int, "PersonTracker"] = Depends(get_trackers),
):
    return await _stream_response(cam_id, request, trackers_map, raw=True)


async def stats_event_source(
    redis, trackers_map: Dict[int, "PersonTracker"], use_stream: bool
) -> AsyncIterator[str]:
    """Yield dashboard stats as SSE events from Redis."""

    from core.stats import gather_stats

    while True:
        try:
            init = gather_stats(trackers_map, redis)
            yield f"data: {json.dumps(init)}\n\n"
            if use_stream:
                last_id = "$"
                while True:
                    try:
                        msgs = await asyncio.to_thread(
                            redis.xread,
                            {"stats_stream": last_id},
                            block=5000,
                            count=1,
                        )
                    except RedisConnectionError:
                        break
                    if msgs:
                        _name, entries = msgs[0]
                        for entry_id, fields in entries:
                            last_id = entry_id
                            raw = fields.get(b"data")
                            if raw is None:
                                continue
                            data = raw.decode()
                            yield f"data: {data}\n\n"
                    else:
                        yield ": ping\n\n"
            else:
                channel = "stats_updates"
                pubsub = redis.pubsub(ignore_subscribe_messages=True)
                try:
                    pubsub.subscribe(channel)
                    q: queue.Queue = queue.Queue()

                    def reader() -> None:
                        try:
                            for msg in pubsub.listen():
                                q.put(msg)
                        except RedisConnectionError:
                            q.put(None)

                    threading.Thread(target=reader, daemon=True).start()
                    last_msg = time.time()
                    while True:
                        try:
                            msg = await asyncio.to_thread(q.get, timeout=5)
                        except queue.Empty:
                            if time.time() - last_msg > 30:
                                try:
                                    pubsub.ping()
                                    last_msg = time.time()
                                except RedisConnectionError:
                                    break
                            yield ": ping\n\n"
                            continue
                        if msg is None:
                            break
                        if msg.get("type") != "message":
                            continue
                        data = msg["data"]
                        if isinstance(data, bytes):
                            data = data.decode()
                        yield f"data: {data}\n\n"
                        last_msg = time.time()
                finally:
                    try:
                        pubsub.close()
                    except Exception:
                        pass
            await asyncio.sleep(1)
        except RedisConnectionError:
            logger.warning("Redis connection failed; retrying")
            await asyncio.sleep(1)


@router.get("/sse/stats")
async def sse_stats(
    request: Request,
    stream: bool | None = Query(None),
    use_stream: bool | None = Query(None),
    cfg: dict = Depends(get_settings),
    trackers_map: Dict[int, "PersonTracker"] = Depends(get_trackers),
    redis=Depends(get_redis),
):
    """Server-Sent Events endpoint for dashboard stats.

    Defaults to using the Redis stream for reliability. Either ``stream`` or
    ``use_stream`` query parameters may toggle the behaviour."""

    if stream is None:
        stream = use_stream if use_stream is not None else True

    return StreamingResponse(
        stats_event_source(redis, trackers_map, stream),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/latest_images")
async def latest_images(
    status: str = "no_helmet",
    count: int = 5,
    redis=Depends(get_redis),
):
    """Return recent PPE snapshots filtered by status."""
    try:
        if asyncio.iscoroutinefunction(redis.zrevrange):
            entries = await redis.zrevrange("ppe_logs", 0, 999)
        else:
            entries = await asyncio.to_thread(redis.zrevrange, "ppe_logs", 0, 999)
    except Exception:
        logger.exception("Failed to fetch latest images")
        entries = []
    imgs: list[str] = []
    for item in entries:
        e = json.loads(item)
        if e.get("status") == status and e.get("path"):
            fname = os.path.basename(e["path"])
            imgs.append(f"/snapshots/{fname}")
            if len(imgs) >= count:
                break
    return {"images": imgs}


@router.get("/api/stats")
async def api_stats(
    trackers_map: Dict[int, "PersonTracker"] = Depends(get_trackers),
    redis=Depends(get_redis),
):
    """Return current dashboard metrics for polling."""
    try:
        if asyncio.iscoroutinefunction(redis.xrevrange):
            entries = await redis.xrevrange("stats_stream", count=1)
        else:
            entries = await asyncio.to_thread(redis.xrevrange, "stats_stream", count=1)
        if entries:
            _id, fields = entries[0]
            raw = fields.get(b"data") or fields.get("data")
            if raw:
                data = raw.decode() if isinstance(raw, (bytes, bytearray)) else raw
                return JSONResponse(content=json.loads(data))
    except Exception:
        logger.exception("Failed to fetch stats from Redis stream")
    from core.stats import gather_stats

    data = gather_stats(trackers_map, redis)
    return JSONResponse(content=data)


@router.get("/api/dashboard/stats")
async def dashboard_stats(
    request: Request,
    range_: Annotated[str, Query(alias="range")] = "7d",
    compare: Annotated[bool, Query()] = False,
    redis=Depends(get_redis),
    cfg: dict = Depends(get_settings),
):
    """Return aggregated dashboard metrics over a timeframe.

    If ``compare`` is true, include metrics for the previous period of equal
    duration under the ``previous`` key.
    """

    start_ts, end_ts = parse_range(range_)
    data = await fetch_stats(redis, start_ts, end_ts)
    result = aggregate_metrics(data)
    result["max_capacity"] = cfg.get("max_capacity", 0)
    return JSONResponse(content=result)


@router.get("/api/camera_info")
async def api_camera_info(
    cams: list = Depends(get_cameras),
    trackers_map: Dict[int, "PersonTracker"] = Depends(get_trackers),
):
    """Return camera backend information for debugging."""
    data = []
    for cam in cams:
        tr = trackers_map.get(cam["id"])
        info = {
            "id": cam["id"],
            "name": cam["name"],
            "backend": tr.capture_backend if tr else None,
            "pipeline": tr.pipeline_info if tr else "",
            "ppe_running": bool(tr and any(t in PPE_TASKS for t in tr.tasks)),
            "stream_status": getattr(tr, "stream_status", ""),
            "stream_error": getattr(tr, "stream_error", ""),
        }
        data.append(info)
    return {"cameras": data}
