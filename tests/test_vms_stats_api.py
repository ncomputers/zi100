"""Validate VMS stats API returns expected keys."""


def test_vms_stats_api(client):
    resp = client.get("/api/vms/stats", params={"range": "7d"})
    assert resp.status_code == 200
    data = resp.json()
    expected = [
        "occupancy",
        "peak_hour",
        "total_invites",
        "busiest_day",
        "avg_duration",
        "returning_pct",
        "visitor_daily",
        "top_employees",
        "top_visitors",
    ]
    for key in expected:
        assert key in data


def test_vms_stats_timeframes(client):
    import json
    import time

    r = client.app.state.redis_client
    r.flushdb()
    import routers.entry as entry

    entry.redis = r
    now = int(time.time())
    old = {"ts": now - 3 * 86400, "name": "Old"}
    recent = {"ts": now, "name": "Recent"}
    r.zadd("vms_logs", {json.dumps(old): old["ts"], json.dumps(recent): recent["ts"]})

    week = client.get("/api/vms/stats", params={"range": "7d"}).json()
    today = client.get("/api/vms/stats", params={"range": "1d"}).json()

    assert sum(d["count"] for d in week["visitor_daily"]) >= sum(
        d["count"] for d in today["visitor_daily"]
    )
