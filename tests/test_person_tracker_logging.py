"""Purpose: Ensure process logging is throttled."""

import sys
from pathlib import Path

from loguru import logger

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from modules.tracker import PersonTracker


def test_log_interval_throttling(monkeypatch):
    tracker = PersonTracker.__new__(PersonTracker)
    tracker.cam_id = 1
    tracker.log_interval = 3
    tracker._log_count = 0
    logs = []
    monkeypatch.setattr(logger, "debug", lambda msg: logs.append(msg))
    for _ in range(5):
        tracker._log_process_interval(0.1)
    assert len(logs) == 1
