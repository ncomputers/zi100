"""Unit tests for entry analytics helpers."""

import json
import time
from datetime import datetime, timedelta

from routers.entry_stats import (
    collect_logs,
    compute_avg_duration,
    compute_busiest_day,
    compute_daily_counts,
    compute_occupancy,
    compute_peak_hour,
    compute_returning_pct,
    compute_top_counts,
    get_total_invites,
)


def test_collect_logs(redis_client):
    now = int(time.time())
    log = {"ts": now, "name": "A"}
    redis_client.zadd("vms_logs", {json.dumps(log): now})
    logs = collect_logs(redis_client, now - 1, now + 1)
    assert logs == [log]


def test_compute_occupancy():
    now = 100
    logs = [
        {"ts": 90, "valid_to": 110},
        {"ts": 50, "valid_to": 80},
    ]
    assert compute_occupancy(logs, now) == 1


def test_compute_avg_duration():
    logs = [
        {"ts": 0, "valid_to": 7200},  # 2h
        {"ts": 0, "valid_to": 3600},  # 1h
    ]
    assert compute_avg_duration(logs) == "1h 30m"


def test_compute_peak_hour():
    base = datetime(2024, 1, 1, 10)
    logs = [
        {"ts": int(base.timestamp())},
        {"ts": int((base + timedelta(days=1)).timestamp())},
        {"ts": int((base - timedelta(hours=1)).timestamp())},
    ]
    assert compute_peak_hour(logs) == "10 AM"


def test_compute_returning_pct():
    logs = [
        {"ts": 0, "name": "A"},
        {"ts": 1, "name": "A"},
        {"ts": 2, "name": "B"},
    ]
    assert compute_returning_pct(logs) == 33


def test_compute_busiest_day():
    monday = datetime(2024, 1, 1)  # Monday
    tuesday = monday + timedelta(days=1)
    logs = [
        {"ts": int(monday.timestamp())},
        {"ts": int(monday.timestamp()) + 1},
        {"ts": int(tuesday.timestamp())},
    ]
    assert compute_busiest_day(logs) == "Monday"


def test_compute_daily_counts():
    start = datetime(2024, 1, 1)
    logs = [
        {"ts": int(start.timestamp())},
        {"ts": int((start + timedelta(days=1)).timestamp())},
        {"ts": int((start + timedelta(days=1)).timestamp()) + 1},
    ]
    res = compute_daily_counts(
        logs, int(start.timestamp()), int((start + timedelta(days=2)).timestamp())
    )
    assert res[0]["count"] == 1
    assert res[1]["count"] == 2
    assert len(res) == 3


def test_compute_top_counts():
    logs = [
        {"host": "A"},
        {"host": "A"},
        {"host": "B"},
    ]
    top = compute_top_counts(logs, "host")
    assert top[0] == {"name": "A", "count": 2}


def test_get_total_invites(redis_client):
    redis_client.zadd("visit_requests", {"a": 1, "b": 2})
    assert get_total_invites(redis_client) == 2
