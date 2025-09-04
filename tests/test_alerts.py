"""Purpose: Test alerts module."""

import asyncio
import json
from pathlib import Path

import fakeredis
import pytest
from fastapi.templating import Jinja2Templates

ROOT = Path(__file__).resolve().parents[1]
import sys

sys.path.insert(0, str(ROOT))

from modules import alerts as alerts_module
from routers import alerts


# DummyRequest class encapsulates dummyrequest behavior
class DummyRequest:
    # __init__ routine
    def __init__(self, data=None):
        self.session = {"user": {"role": "admin"}}
        self._data = data or {}

    async def json(self):
        return self._data


# Test alerts page metrics
def test_alerts_page_metrics(tmp_path):
    cfg = {"alert_rules": [], "email": {}, "features": {"visitor_mgmt": True}}
    (tmp_path / "email_alerts.html").write_text("{{ anomaly_items }}")
    templates = Jinja2Templates(directory=str(tmp_path))
    req = DummyRequest()
    resp = asyncio.run(alerts.alerts_page(req, cfg=cfg, templates=templates))
    html = resp.body.decode()
    assert "visitor_registered" in html


# Test alert worker vms
def test_alert_worker_vms(tmp_path, monkeypatch):
    calls = []

    # mock_send routine
    def mock_send(*a, **k):
        calls.append(a)
        return True, None

    monkeypatch.setattr(alerts_module, "send_email", mock_send)
    r = fakeredis.FakeRedis()
    cfg = {
        "alert_rules": [
            {
                "metric": "visitor_registered",
                "type": "event",
                "value": 1,
                "recipients": "a@example.com",
            }
        ],
        "email": {},
        "email_enabled": True,
    }
    worker = alerts_module.AlertWorker(cfg, "redis://localhost", tmp_path)
    worker.redis = r
    r.zadd(
        "vms_logs",
        {
            json.dumps(
                {"ts": 1, "name": "A", "gate_id": "GP1", "host": "H", "phone": "1"}
            ): 1
        },
    )
    worker.check_rules()
    assert calls


def test_save_alerts_validation(client):
    resp = client.post(
        "/alerts",
        json={"rules": [{"metric": "bad", "value": 1, "recipients": "a@example.com"}]},
    )
    assert resp.status_code == 400
    resp = client.post(
        "/alerts",
        json={
            "rules": [
                {"metric": "no_helmet", "value": 0, "recipients": "a@example.com"}
            ]
        },
    )
    assert resp.status_code == 400
    resp = client.post(
        "/alerts",
        json={"rules": [{"metric": "no_helmet", "value": 1, "recipients": "bad"}]},
    )
    assert resp.status_code == 400
    ok = client.post(
        "/alerts",
        json={
            "rules": [
                {"metric": "no_helmet", "value": 1, "recipients": "a@example.com"}
            ]
        },
    )
    assert ok.status_code == 200 and ok.json()["saved"]


def test_update_email_validation(client):
    resp = client.post("/email", json={"from_addr": "not-an-email"})
    assert resp.status_code == 400
    ok = client.post("/email", json={"from_addr": "test@example.com"})
    assert ok.status_code == 200 and ok.json()["saved"]
