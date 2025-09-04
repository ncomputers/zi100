"""Count report routes."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Dict, List

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from loguru import logger

from config import config
from modules import export
from modules.utils import require_roles
from schemas.report import ReportQuery
from utils.pagination import paginate
from utils.time import format_ts

router = APIRouter()

BASE_DIR = Path(__file__).resolve().parent.parent


# init_context routine
def init_context(
    config: dict,
    trackers: Dict[int, "PersonTracker"],
    redis_client,
    templates_path,
    cameras: List[dict],
) -> None:
    """Initialize shared context for report routes."""
    global cfg, trackers_map, redis, templates, cams
    cfg = config
    trackers_map = trackers
    redis = redis_client
    templates = Jinja2Templates(directory=templates_path)
    cams = cameras


@router.get("/report")
async def report_page(
    request: Request,
    type: str = "person",
    range: str = "",
    include_archived: bool = False,
):
    res = require_roles(request, ["admin"])
    if isinstance(res, RedirectResponse):
        return res
    no_data = True
    try:
        if (
            redis.zcard("history")
            or redis.zcard("person_logs")
            or redis.zcard("vehicle_logs")
        ):
            no_data = False
    except Exception:
        pass
    quick_map = {"7d": "week", "this_month": "month"}
    selected_quick = quick_map.get(range, range)
    cam_list = cams if include_archived else [c for c in cams if not c.get("archived")]
    return templates.TemplateResponse(
        "report.html",
        {
            "request": request,
            "vehicle_enabled": "vehicle" in cfg.get("track_objects", []),
            "face_enabled": "face" in cfg.get("track_objects", []),
            "plate_enabled": "number_plate" in cfg.get("track_objects", []),
            "cameras": cam_list,
            "labels": cfg.get("count_classes", []),
            "cfg": config,
            "no_data": no_data,
            "selected_type": type,
            "selected_quick": selected_quick,
            "include_archived": include_archived,
        },
    )


async def _report_data(query: ReportQuery):
    start_ts = int(query.start.timestamp())
    end_ts = int(query.end.timestamp())
    if query.view == "graph":

        entries = [
            json.loads(e) for e in redis.zrangebyscore("history", start_ts, end_ts)
        ]
        times, ins, outs, currents = [], [], [], []
        key_in = f"in_{query.type}"
        key_out = f"out_{query.type}"
        prev_in, prev_out = 0, 0
        for entry in entries:
            ts = entry.get("ts")
            times.append(format_ts(ts, "%Y-%m-%d %H:%M"))
            i = entry.get(key_in, 0)
            o = entry.get(key_out, 0)
            ins.append(i - prev_in)
            outs.append(o - prev_out)
            currents.append(i - o)
            prev_in, prev_out = i, o
        data = {"times": times, "ins": ins, "outs": outs, "current": currents}
    else:
        if query.type == "person":
            key = "person_logs"
        elif query.type == "vehicle":
            key = "vehicle_logs"
        else:
            key = "person_logs"
        entries = [json.loads(e) for e in redis.zrevrangebyscore(key, end_ts, start_ts)]

        if query.cam_id is not None:
            entries = [e for e in entries if e.get("cam_id") == query.cam_id]
        if query.label:
            entries = [e for e in entries if e.get("label") == query.label]

        page_num = (max(query.cursor, 0) // query.rows) + 1
        page_entries = paginate(entries, page_num, query.rows)
        next_cursor = (
            query.cursor + query.rows
            if query.cursor + query.rows < len(entries)
            else None
        )

        rows_out = []
        for e in page_entries:
            ts = e.get("ts")
            img_url = None
            path = e.get("path")
            if path:
                img_url = f"/snapshots/{os.path.basename(path)}"
            plate_url = None
            plate = e.get("plate_path")
            if plate:
                plate_url = f"/snapshots/{os.path.basename(plate)}"
            row = {
                "time": format_ts(ts, "%Y-%m-%d %H:%M"),
                "cam_id": e.get("cam_id"),
                "track_id": e.get("track_id"),
                "direction": e.get("direction"),
                "path": img_url,
                "plate_path": plate_url,
                "label": e.get("label"),
            }
            rows_out.append(row)
        data = {"rows": rows_out, "next_cursor": next_cursor}

    return data


@router.get("/report_data")
async def report_data(query: ReportQuery = Depends(), request: Request = None):
    res = require_roles(request, ["admin"])
    if isinstance(res, RedirectResponse):
        return res
    return await _report_data(query)


@router.get("/report/export")
async def report_export(query: ReportQuery = Depends(), request: Request = None):
    res = require_roles(request, ["admin"])
    if isinstance(res, RedirectResponse):
        return res
    data = await _report_data(query)
    if query.view == "graph":
        try:
            columns = [
                ("time", "Time"),
                ("in", "In"),
                ("out", "Out"),
                ("current", "Current"),
            ]
            rows = [
                {"time": t, "in": i, "out": o, "current": c}
                for t, i, o, c in zip(
                    data["times"], data["ins"], data["outs"], data["current"]
                )
            ]
            return export.export_csv(rows, columns, "count_report")
        except Exception as exc:
            logger.exception("report export failed: {}", exc)
            return JSONResponse(
                {"status": "error", "reason": "export_failed"}, status_code=500
            )
    else:
        rows = data["rows"]
        for row in rows:
            if row.get("path"):
                row["img_file"] = os.path.join(BASE_DIR, row["path"].lstrip("/"))
            if row.get("plate_path"):
                row["plate_file"] = os.path.join(
                    BASE_DIR, row["plate_path"].lstrip("/")
                )
        columns = [
            ("time", "Time"),
            ("cam_id", "Camera"),
            ("track_id", "Track"),
            ("direction", "Direction"),
        ]
        if query.type == "face":
            columns.append(("label", "Face ID"))
        else:
            columns.append(("label", "Label"))
        try:
            # export first image column, ignore second due to simplicity
            img_label = "Snapshot" if query.type == "face" else "Image"
            return export.export_excel(
                rows,
                columns,
                "count_report",
                image_key="img_file",
                image_label=img_label,
            )
        except Exception as exc:
            logger.exception("report export failed: {}", exc)
            return JSONResponse(
                {"status": "error", "reason": "export_failed"}, status_code=500
            )
