"""Utilities for collecting and aggregating system statistics."""

from __future__ import annotations

import json
from typing import Dict

import redis

from config import config

from .config import ANOMALY_ITEMS, COUNT_GROUPS


# gather_stats routine
def gather_stats(trackers: Dict[int, "PersonTracker"], r: redis.Redis) -> dict:
    """Collect aggregated counts and anomaly metrics."""
    group_counts = {}
    for g in COUNT_GROUPS.keys():
        in_c = sum(t.in_counts.get(g, 0) for t in trackers.values())
        out_c = sum(t.out_counts.get(g, 0) for t in trackers.values())
        group_counts[g] = {"in": in_c, "out": out_c, "current": in_c - out_c}
    count_keys = [f"{item}_count" for item in ANOMALY_ITEMS]
    count_vals = r.mget(count_keys)
    anomaly_counts = {
        item: int(val or 0) for item, val in zip(ANOMALY_ITEMS, count_vals)
    }
    max_cap = config.get("max_capacity", 0)
    warn_lim = max_cap * config.get("warn_threshold", 0) / 100
    current = group_counts.get("person", {}).get("current", 0)
    status = "green" if current < warn_lim else "yellow" if current < max_cap else "red"
    return {
        "in_count": group_counts.get("person", {}).get("in", 0),
        "out_count": group_counts.get("person", {}).get("out", 0),
        "current": current,
        "max_capacity": max_cap,
        "status": status,
        "anomaly_counts": anomaly_counts,
        "group_counts": group_counts,
    }


# broadcast_stats routine
def broadcast_stats(trackers: Dict[int, "PersonTracker"], r: redis.Redis) -> None:
    """Publish the latest stats if totals changed."""
    data = gather_stats(trackers, r)

    try:
        raw_totals = r.hgetall("stats_totals") or {}
    except redis.RedisError:
        raw_totals = {}

    existing: dict = {}
    for k, v in raw_totals.items():
        key = k.decode() if isinstance(k, (bytes, bytearray)) else k
        val = v.decode() if isinstance(v, (bytes, bytearray)) else v
        if key in {"anomaly_counts", "group_counts"}:
            try:
                existing[key] = json.loads(val)
            except Exception:  # pragma: no cover - corrupt data
                existing[key] = {}
        else:
            try:
                existing[key] = int(val)
            except (TypeError, ValueError):
                existing[key] = val

    if (
        data.get("in_count", 0) == existing.get("in_count", 0)
        and data.get("out_count", 0) == existing.get("out_count", 0)
        and data.get("current", 0) == existing.get("current", 0)
        and data.get("anomaly_counts", {}) == existing.get("anomaly_counts", {})
        and data.get("group_counts", {}) == existing.get("group_counts", {})
    ):
        return

    payload = json.dumps(data)
    r.publish("stats_updates", payload)
    try:
        r.hset(
            "stats_totals",
            mapping={
                "in_count": data["in_count"],
                "out_count": data["out_count"],
                "current": data["current"],
                "max_capacity": data["max_capacity"],
                "status": data["status"],
                "anomaly_counts": json.dumps(data["anomaly_counts"]),
                "group_counts": json.dumps(data["group_counts"]),
            },
        )
        r.xadd("stats_stream", {"data": payload}, maxlen=1, approximate=False)
    except redis.ResponseError:
        # stream might not exist or be trimmed incorrectly
        pass
