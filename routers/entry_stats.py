from __future__ import annotations

import json
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from typing import Dict, Iterable, List


def collect_logs(redis_client, start_ts: int, end_ts: int) -> List[Dict]:
    """Fetch visitor logs from redis within the given time window."""
    entries = redis_client.zrangebyscore("vms_logs", start_ts, end_ts)
    return [json.loads(e) for e in entries]


def compute_occupancy(logs: Iterable[Dict], now: int) -> int:
    """Return number of active visits at *now*."""
    return sum(
        1 for e in logs if e.get("valid_from", e["ts"]) <= now <= e.get("valid_to", now)
    )


def compute_avg_duration(logs: Iterable[Dict]) -> str:
    """Return average visit duration formatted as 'Xh Ym' or 'Xm'."""
    dur_total = 0
    dur_count = 0
    for e in logs:
        start = e.get("valid_from", e["ts"])
        end = e.get("valid_to", start)
        if end >= start:
            dur_total += end - start
            dur_count += 1
    avg_duration_min = int(dur_total / max(1, dur_count) / 60)
    if avg_duration_min >= 60:
        return f"{avg_duration_min // 60}h {avg_duration_min % 60}m"
    return f"{avg_duration_min}m"


def compute_peak_hour(logs: Iterable[Dict]) -> str:
    """Return hour of day with most visits as 'H AM/PM'."""
    hours = Counter(datetime.fromtimestamp(e["ts"]).strftime("%H") for e in logs)
    if not hours:
        return ""
    peak_key = max(hours, key=hours.get)
    return datetime.strptime(peak_key, "%H").strftime("%I %p").lstrip("0")


def compute_returning_pct(logs: Iterable[Dict]) -> int:
    """Return percentage of returning visitors based on name duplicates."""
    names = [e.get("name") for e in logs if e.get("name")]
    unique = len(set(names))
    return int(((len(names) - unique) / len(names)) * 100) if names else 0


def compute_busiest_day(logs: Iterable[Dict]) -> str:
    """Return day of week with most visits."""
    days = Counter(datetime.fromtimestamp(e["ts"]).strftime("%A") for e in logs)
    return max(days, key=days.get) if days else ""


def compute_daily_counts(
    logs: Iterable[Dict], start_ts: int, end_ts: int
) -> List[Dict]:
    """Return list of daily visitor counts limited to two weeks."""
    start_date = datetime.fromtimestamp(start_ts).date()
    days_range = max(1, int((end_ts - start_ts) / 86400) + 1)
    days_range = min(14, days_range)
    daily = defaultdict(int)
    for e in logs:
        d = datetime.fromtimestamp(e["ts"]).date().isoformat()
        daily[d] += 1
    return [
        {
            "date": (start_date + timedelta(days=i)).isoformat(),
            "count": daily.get((start_date + timedelta(days=i)).isoformat(), 0),
        }
        for i in range(days_range)
    ]


def compute_top_counts(logs: Iterable[Dict], key: str, top_n: int = 5) -> List[Dict]:
    """Return top *top_n* values for *key* with counts."""
    counts = Counter(e.get(key, "") for e in logs if e.get(key))
    return [{"name": n, "count": c} for n, c in counts.most_common(top_n)]


def get_total_invites(redis_client) -> int:
    """Return total visit requests."""
    return int(redis_client.zcard("visit_requests"))
