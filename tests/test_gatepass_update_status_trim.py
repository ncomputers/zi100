"""Ensure update_status trims log entries without errors."""

import json
import sys
import time
from pathlib import Path

import fakeredis

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from modules import gatepass_service


def test_update_status_trims_logs():
    r = fakeredis.FakeRedis()
    gatepass_service.init(r)
    gate_id = "GP1"
    now = int(time.time())
    obj = {"gate_id": gate_id, "status": "pending", "ts": now}
    r.hset("gatepass:active", gate_id, json.dumps(obj))
    r.zadd("vms_logs", {json.dumps(obj): now})
    r.zadd("vms_logs", {"old": 0})

    gatepass_service.update_status(gate_id, "approved")

    entries = r.zrange("vms_logs", 0, -1)
    assert len(entries) == 1
    rec = json.loads(entries[0])
    assert rec["gate_id"] == gate_id
    assert rec["status"] == "approved"
