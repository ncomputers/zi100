from __future__ import annotations

import base64
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

visitor = sys.modules[__package__]


def load_faces(
    set_key: str,
    fields_map: dict[str, Any],
    limit: int,
    cursor: int | None = None,
    q: str | None = None,
    camera_id: str | None = None,
    last_seen_after: int | None = None,
) -> tuple[list[dict], int | None]:
    """Query Redis for faces with cursor-based pagination."""

    ctx = visitor.get_context()
    redis = ctx.redis
    prefix: str = fields_map.get("prefix", "")
    field_funcs: dict[str, Callable[[str, dict, int, str, str], Any]] = fields_map.get(
        "fields", {}
    )

    max_score = cursor if cursor is not None else "+inf"
    if cursor is not None:
        max_score = f"({cursor}"
    raw_ids = redis.zrevrangebyscore(
        set_key, max_score, "-inf", start=0, num=limit * 5 + 1
    )

    faces: list[tuple[dict, int]] = []
    next_cursor: int | None = None
    q_l = q.lower() if q else None
    has_more = False

    for idx, fid in enumerate(raw_ids):
        fid_str = fid.decode() if isinstance(fid, bytes) else fid
        key = f"{prefix}{fid_str}"
        raw_fields = redis.hgetall(key)
        fields = {
            k.decode() if isinstance(k, bytes) else k: (
                v.decode() if isinstance(v, bytes) else v
            )
            for k, v in raw_fields.items()
        }

        last_seen = fields.get("last_seen_at") or fields.get("created_at") or "0"
        try:
            ts = int(last_seen)
        except Exception:
            ts = 0
        if last_seen_after is not None and ts < last_seen_after:
            continue
        if camera_id and fields.get("camera_id") != camera_id:
            continue
        if q_l:
            target = " ".join(
                fields.get(k, "") for k in ("name", "email", "phone", "visitor_id")
            ).lower()
            if q_l not in target:
                continue

        date_str = ""
        if ts:
            try:
                date_str = datetime.fromtimestamp(ts).strftime("%d-%b-%Y")
            except Exception:
                date_str = ""

        img_b64 = fields.get("image") or fields.get("image_b64", "")
        img_path = fields.get("image_path")
        if not img_b64 and img_path and Path(img_path).exists():
            with open(img_path, "rb") as f:
                img_b64 = base64.b64encode(f.read()).decode()

        info = {
            out: func(fid_str, fields, ts, date_str, img_b64)
            for out, func in field_funcs.items()
        }
        faces.append((info, ts))
        if len(faces) >= limit:
            if idx < len(raw_ids) - 1:
                has_more = True
            break

    if has_more and faces:
        next_cursor = faces[-1][1]

    return [f[0] for f in faces], next_cursor
