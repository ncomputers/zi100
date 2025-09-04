"""Purpose: Test ppe worker module."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import json

from modules.ppe_worker import PPEDetector, _fetch_job, determine_status


# Test determine status
def test_determine_status():
    scores = {"helmet": 0.6}
    status, conf = determine_status(scores, "helmet", 0.5)
    assert status == "helmet"
    assert conf == 0.6

    scores = {"no_helmet": 0.7}
    status, conf = determine_status(scores, "helmet", 0.5)
    assert status == "no_helmet"
    assert conf == 0.7


def test_determine_status_normalizes_no_prefix():
    scores = {"helmet": 0.6}
    status, conf = determine_status(scores, "no_helmet", 0.5)
    assert status == "helmet"
    assert conf == 0.6


def test_duplicate_logging_cooldown():
    det = PPEDetector.__new__(PPEDetector)
    det.cfg = {"duplicate_bypass_seconds": 5}
    det._last_status_ts = {}
    assert det._should_log(1, "no_helmet", 100)
    assert not det._should_log(1, "no_helmet", 102)
    assert det._should_log(1, "no_helmet", 106)


class _Redis:
    def __init__(self, payload):
        self.payload = payload

    def brpop(self, _name, timeout=0):  # pragma: no cover - simple helper
        return self.payload


def test_fetch_job_none():
    assert _fetch_job(_Redis(None)) is None


def test_fetch_job_parses_json():
    payload = ("ppe_queue", json.dumps({"a": 1}))
    assert _fetch_job(_Redis(payload)) == {"a": 1}
