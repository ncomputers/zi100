import asyncio
import json
import sys
import time
from datetime import datetime
from pathlib import Path

import fakeredis
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# Stub heavy deps
sys.modules.setdefault("cv2", type("cv2", (), {}))
sys.modules.setdefault(
    "torch",
    type("torch", (), {"cuda": type("cuda", (), {"is_available": lambda: False})}),
)
sys.modules.setdefault("ultralytics", type("ultralytics", (), {"YOLO": object}))
sys.modules.setdefault("deep_sort_realtime", type("ds", (), {}))
sys.modules["deep_sort_realtime.deepsort_tracker"] = type("t", (), {"DeepSort": object})

from routers import ppe_reports, reports
from schemas.ppe_report import PPEReportQuery
from schemas.report import ReportQuery


@pytest.fixture
def redis_client():
    return fakeredis.FakeRedis()


@pytest.fixture
def cfg():
    return {
        "track_objects": ["person"],
        "track_ppe": ["helmet"],
        "helmet_conf_thresh": 0.5,
    }


@pytest.fixture(autouse=True)
def setup_context(redis_client, cfg, tmp_path):
    reports.init_context(cfg, {}, redis_client, str(tmp_path), [])
    ppe_reports.init_context(cfg, {}, redis_client, str(tmp_path))


def test_ppe_queue_does_not_clear_person_logs(redis_client):
    now = int(time.time())
    entry = {
        "ts": now,
        "cam_id": 1,
        "track_id": 1,
        "direction": "in",
        "label": "person",
        "path": "a.jpg",
    }
    redis_client.zadd("person_logs", {json.dumps(entry): entry["ts"]})
    redis_client.zadd("ppe_queue", {json.dumps(entry): entry["ts"]})

    # simulate PPEDetector consuming from PPE queue
    redis_client.zpopmin("ppe_queue")

    # person_logs entry should still exist
    query = ReportQuery(
        start=datetime.fromtimestamp(now - 1),
        end=datetime.fromtimestamp(now + 1),
        type="person",
        view="table",
        rows=10,
    )
    data = asyncio.run(reports._report_data(query))
    assert len(data["rows"]) == 1
    assert data["rows"][0]["track_id"] == 1

    # ppe_worker would push anomaly results to ppe_logs
    anomaly = {
        "ts": now + 1,
        "cam_id": 1,
        "track_id": 1,
        "status": "no_helmet",
        "conf": 0.9,
        "path": "a.jpg",
    }
    redis_client.zadd("ppe_logs", {json.dumps(anomaly): anomaly["ts"]})

    ppe_query = PPEReportQuery(
        start=datetime.fromtimestamp(now - 1),
        end=datetime.fromtimestamp(now + 2),
        status=["no_helmet"],
    )
    ppe_data = asyncio.run(ppe_reports.ppe_report_data(ppe_query))
    assert len(ppe_data["rows"]) == 1
    assert ppe_data["rows"][0]["status"] == "no_helmet"
