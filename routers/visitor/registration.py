"""Visitor registration and reporting routes."""

from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import JSONResponse, RedirectResponse
from loguru import logger

from config import config
from modules import export, visitor_db
from modules.utils import require_admin
from schemas.visitor import VisitorRegisterForm
from utils.ids import generate_id
from utils.image import decode_base64_image
from utils.pagination import paginate

from ..visitor_utils import visitor_disabled_response
from . import (
    VISITOR_LOG_RETENTION_SECS,
    _save_host_master,
    _save_visitor_master,
    _trim_visitor_logs,
    get_context,
)

ctx = get_context()
config_obj = ctx.config
redis = ctx.redis

router = APIRouter()


async def _fetch_visitors(
    start_dt: datetime | None,
    end_dt: datetime | None,
    vtype: str | None,
    include_pending: bool,
) -> list[dict]:
    """Retrieve visitor and gatepass entries from Redis."""
    if not redis:
        raise HTTPException(status_code=503, detail="redis_unavailable")
    local_tz = datetime.now().astimezone().tzinfo
    min_ts = (
        int(start_dt.astimezone(timezone.utc).timestamp())
        if start_dt
        else float("-inf")
    )
    max_ts = (
        int(end_dt.astimezone(timezone.utc).timestamp()) if end_dt else float("inf")
    )
    try:
        visitor_entries = redis.zrevrangebyscore("visitor_logs", max_ts, min_ts)
        gate_entries = redis.zrevrangebyscore("vms_logs", max_ts, min_ts)
    except Exception as exc:  # pragma: no cover - redis errors
        logger.error("Failed retrieving visitor logs: {}", exc)
        raise HTTPException(status_code=500, detail="redis_error")

    combined: list[tuple[datetime, dict]] = []
    allowed_status = {
        "pending",
        "approved",
        "meeting in progress",
        "completed",
        "expired",
    }

    def process(entry: bytes | str) -> None:
        item = json.loads(entry if isinstance(entry, str) else entry.decode())
        status = item.get("status", "").lower()
        if status not in allowed_status or (
            not include_pending and status == "pending"
        ):
            return
        ts_val = item.get("time") or item.get("created") or item.get("ts") or 0
        try:
            if isinstance(ts_val, str):
                try:
                    ts = datetime.strptime(ts_val, "%Y-%m-%d %H:%M:%S").replace(
                        tzinfo=local_tz
                    )
                except Exception:
                    ts = datetime.fromtimestamp(
                        int(ts_val), tz=timezone.utc
                    ).astimezone(local_tz)
            else:
                ts = datetime.fromtimestamp(int(ts_val), tz=timezone.utc).astimezone(
                    local_tz
                )
        except Exception:
            return
        if start_dt and ts < start_dt:
            return
        if end_dt and ts > end_dt:
            return
        if vtype and item.get("visitor_type") != vtype:
            return
        combined.append(
            (
                ts,
                {
                    "gate_id": item.get("gate_id"),
                    "name": item.get("name"),
                    "phone": item.get("phone"),
                    "host": item.get("host"),
                    "visitor_type": item.get("visitor_type"),
                    "purpose": item.get("purpose"),
                    "time": ts.strftime("%Y-%m-%d %H:%M"),
                },
            )
        )

    for e in visitor_entries:
        process(e)
    for e in gate_entries:
        process(e)

    seen: set[tuple] = set()
    deduped: list[tuple[datetime, dict]] = []
    for ts, rec in combined:
        key = (
            rec.get("gate_id"),
            rec.get("name"),
            rec.get("phone"),
            rec.get("host"),
            rec.get("visitor_type"),
            rec.get("purpose"),
            rec.get("time"),
        )
        if key in seen:
            continue
        seen.add(key)
        deduped.append((ts, rec))

    deduped.sort(key=lambda x: x[0], reverse=True)
    return [rec for _, rec in deduped]


@router.get("/api/visitor-report")
@router.get("/api/visitors")
async def api_visitor_report(
    start_date: str | None = None,
    end_date: str | None = None,
    vtype: str | None = Query(None, alias="type"),
    include_pending: bool = Query(False, alias="include_pending"),
    view: str = "pass",
    page: int = 1,
    page_size: int = 100,
):
    """Return visitor records with optional grouping."""
    if not config_obj.get("features", {}).get("visitor_mgmt"):
        return visitor_disabled_response()

    if not redis:
        raise HTTPException(status_code=503, detail="redis_unavailable")

    local_tz = datetime.now().astimezone().tzinfo

    def parse_date(val: str | None, end: bool = False) -> datetime | None:
        if not val:
            return None
        try:
            dt = datetime.fromisoformat(val)
        except ValueError as exc:  # pragma: no cover - validation
            raise HTTPException(status_code=400, detail="invalid_date") from exc
        dt = dt.replace(tzinfo=local_tz)
        if end:
            return dt.replace(hour=23, minute=59, second=59, microsecond=999000)
        return dt.replace(hour=0, minute=0, second=0, microsecond=0)

    start_dt = parse_date(start_date)
    end_dt = parse_date(end_date, end=True)
    if start_dt and end_dt and (end_dt - start_dt).days > 90:
        raise HTTPException(status_code=400, detail="span_too_large")

    records = await _fetch_visitors(start_dt, end_dt, vtype, include_pending)

    if view == "pass":
        grouped = records
    elif view == "visitor":
        counts: dict[tuple[str, str], dict] = {}
        for r in records:
            key = (r.get("name") or "", r.get("phone") or "")
            info = counts.setdefault(
                key, {"name": key[0] or "Unknown", "phone": key[1], "visits": 0}
            )
            info["visits"] += 1
        grouped = list(counts.values())
        grouped.sort(key=lambda x: x["visits"], reverse=True)
    elif view == "host":
        mapping: dict[str, set] = {}
        for r in records:
            host = r.get("host") or "Unknown"
            key = (r.get("name"), r.get("phone"))
            mapping.setdefault(host, set()).add(key)
        grouped = [
            {"host": host, "visitors": len(visitors)}
            for host, visitors in mapping.items()
        ]
        grouped.sort(key=lambda x: x["visitors"], reverse=True)
    else:
        raise HTTPException(status_code=400, detail="invalid_view")

    total = len(grouped)
    items = paginate(grouped, page, page_size)
    return {"items": items, "page": page, "page_size": page_size, "total": total}


@router.get("/visitor_register")
async def visitor_register_form(
    request: Request,
    face_id: str,
    user=Depends(require_admin),
    ctx: SimpleNamespace = Depends(get_context),
):
    if not config_obj.get("features", {}).get("visitor_mgmt"):
        return RedirectResponse("/", status_code=302)
    raw = redis.get(f"visitor_log:{face_id}")
    if not raw:
        return RedirectResponse("/visitor_report", status_code=302)
    item = json.loads(raw if isinstance(raw, str) else raw.decode())
    return ctx.templates.TemplateResponse(
        "visitor_register.html", {"request": request, "record": item}
    )


async def _update_visitor_log(form: VisitorRegisterForm) -> dict:
    if redis is None:
        raise HTTPException(status_code=500, detail="redis_unavailable")
    if not config_obj.get("features", {}).get("visitor_mgmt"):
        raise HTTPException(status_code=403, detail="visitor_mgmt_disabled")
    raw = redis.get(f"visitor_log:{form.face_id}")
    if not raw:
        raise HTTPException(status_code=404, detail="face_id_not_found")
    record = json.loads(raw if isinstance(raw, str) else raw.decode())
    record.update(
        {
            "name": form.name,
            "phone": form.phone,
            "host": form.host,
            "purpose": form.purpose,
            "visitor_type": form.visitor_type,
        }
    )
    redis.zadd("visitor_logs", {json.dumps(record): record["ts"]})
    redis.set(
        f"visitor_log:{form.face_id}",
        json.dumps(record),
        ex=VISITOR_LOG_RETENTION_SECS,
    )
    await _trim_visitor_logs()
    return record


def _persist_master_records(record: dict) -> None:
    try:
        _save_visitor_master(
            record.get("name", ""),
            "",
            record.get("phone", ""),
            record.get("visitor_type", ""),
            "",
            record.get("photo_url", ""),
        )
        host = record.get("host")
        if host:
            _save_host_master(host)
    except Exception:
        pass


def _promote_embedding(face_id: str, record: dict) -> None:
    if redis is None:
        raise HTTPException(status_code=500, detail="redis_unavailable")
    emb = redis.hget("visitor_embeddings", face_id)
    if not emb:
        return
    embedding = json.loads(emb if isinstance(emb, str) else emb.decode())
    redis.hset("known_visitors", record["name"], json.dumps(embedding))
    img_path = ""
    if record.get("image"):
        try:
            img_path = str(Path("static/faces") / f"{generate_id()}.jpg")
            with open(img_path, "wb") as f:
                f.write(decode_base64_image(record["image"]))
        except Exception:
            img_path = ""
        redis.hset("known_faces", record["name"], record["image"])
    new_id = generate_id()
    redis.hset(
        f"face:known:{new_id}",
        mapping={
            "name": record["name"],
            "embedding": json.dumps(embedding),
            "image_path": img_path,
            "created_at": str(int(time.time())),
        },
    )


@router.post("/visitor_register")
async def visitor_register(
    form: VisitorRegisterForm = Depends(VisitorRegisterForm.as_form),
):
    record = await _update_visitor_log(form)
    _persist_master_records(record)
    _promote_embedding(form.face_id, record)
    return {"saved": True}


@router.get("/api/visitor-report/export")
@router.get("/visitors/export")
async def export_visitor_report(
    start_date: str | None = None,
    end_date: str | None = None,
    vtype: str | None = Query(None, alias="type"),
    include_pending: bool = Query(False, alias="include_pending"),
    view: str = "pass",
):
    if not config_obj.get("features", {}).get("visitor_mgmt"):
        return RedirectResponse("/", status_code=302)

    if not redis:
        raise HTTPException(status_code=503, detail="redis_unavailable")

    local_tz = datetime.now().astimezone().tzinfo

    def parse_date(val: str | None, end: bool = False) -> datetime | None:
        if not val:
            return None
        dt = datetime.fromisoformat(val).replace(tzinfo=local_tz)
        if end:
            return dt.replace(hour=23, minute=59, second=59, microsecond=999000)
        return dt.replace(hour=0, minute=0, second=0, microsecond=0)

    start_dt = parse_date(start_date)
    end_dt = parse_date(end_date, end=True)
    records = await _fetch_visitors(start_dt, end_dt, vtype, include_pending)

    if view == "visitor":
        data = []
        counts: dict[tuple[str, str], dict] = {}
        for r in records:
            key = (r.get("name") or "", r.get("phone") or "")
            info = counts.setdefault(
                key, {"name": key[0] or "Unknown", "phone": key[1], "visits": 0}
            )
            info["visits"] += 1
        data = list(counts.values())
        columns = [("name", "Name"), ("phone", "Phone"), ("visits", "Visits")]
    elif view == "host":
        mapping: dict[str, set] = {}
        for r in records:
            host = r.get("host") or "Unknown"
            key = (r.get("name"), r.get("phone"))
            mapping.setdefault(host, set()).add(key)
        data = [
            {"host": host, "visitors": len(visitors)}
            for host, visitors in mapping.items()
        ]
        columns = [("host", "Host"), ("visitors", "Visitors Met")]
    else:
        data = records
        columns = [
            ("gate_id", "Gate ID"),
            ("name", "Name"),
            ("phone", "Phone"),
            ("host", "Host"),
            ("visitor_type", "Type"),
            ("purpose", "Purpose"),
            ("time", "Time"),
        ]

    try:
        return export.export_csv(data, columns, "visitor_report")
    except Exception as exc:  # pragma: no cover - export errors
        logger.exception("visitor export failed: {}", exc)
        return JSONResponse(
            {"status": "error", "reason": "export_failed"}, status_code=500
        )


@router.get("/visitor_report")
async def visitor_report(request: Request, ctx: SimpleNamespace = Depends(get_context)):
    """Render visitor report page."""
    logged_in = bool(request.session.get("user"))
    return ctx.templates.TemplateResponse(
        "visitor_report.html",
        {"request": request, "cfg": config, "logged_in": logged_in},
    )


@router.get("/visitors")
async def visitors_legacy(request: Request):
    """Legacy route for backward compatibility; redirect to visitor_report."""
    return RedirectResponse("/visitor_report", status_code=302)


@router.get("/api/visitor_lookup")
@router.get("/vms/visitor/lookup")
async def visitor_lookup(phone: str = "", host: str = "") -> dict:
    """Return stored info for auto-fill suggestions."""
    result: dict = {}
    if phone:
        data = visitor_db.get_visitor_by_phone(phone)
        if data:
            result["visitor"] = data
    if host:
        hdata = visitor_db.get_host(host)
        if hdata:
            result["host"] = hdata
    return result


@router.get("/vms/visitor/suggest")
@router.get("/api/visitors/suggest")
async def visitor_suggest(
    prefix: str = Query("", alias="prefix"),
    name_prefix: str = Query("", alias="name_prefix"),
) -> list[dict]:
    """Return visitors whose names start with the given prefix."""
    q = prefix or name_prefix
    return visitor_db.search_visitors_by_name(q)


@router.get("/custom_report")
async def custom_report(
    mode: str = "visitor",
    start: str | None = None,
    end: str | None = None,
    export_csv: bool = False,
):
    if not config_obj.get("features", {}).get("visitor_mgmt"):
        return visitor_disabled_response()
    start_ts = int(datetime.fromisoformat(start).timestamp()) if start else 0
    end_ts = int(datetime.fromisoformat(end).timestamp()) if end else 2**31
    entries = redis.zrevrange("vms_logs", 0, -1)
    stats: dict[str, dict] = {}
    for e in entries:
        item = json.loads(e)
        ts = item["ts"]
        if not (start_ts <= ts <= end_ts):
            continue
        if mode == "visitor":
            key = item.get("name")
            other = item.get("host")
        else:
            key = item.get("host")
            other = item.get("name")
        if not key:
            continue
        info = stats.setdefault(key, {"count": 0, "last": 0, "map": {}})
        info["count"] += 1
        info["last"] = max(info["last"], ts)
        if other:
            info["map"][other] = info["map"].get(other, 0) + 1
    rows = []
    for key, info in stats.items():
        freq = max(info["map"], key=info["map"].get) if info["map"] else ""
        rows.append(
            {
                "name": key,
                "count": info["count"],
                "last": datetime.fromtimestamp(info["last"]).isoformat(
                    sep=" ", timespec="seconds"
                ),
                "frequent": freq,
            }
        )
    if export_csv:
        cols = [
            ("name", "Visitor" if mode == "visitor" else "Host"),
            ("count", "Visits"),
            ("last", "Last"),
            ("frequent", "Frequent"),
        ]
        return export.export_csv(rows, cols, f"{mode}_report")
    return {"rows": rows}
