from datetime import datetime

import pytest

from utils.time import format_ts, parse_range


def test_format_ts_default():
    assert format_ts(0) == "1970-01-01 00:00:00"


def test_format_ts_custom_format():
    assert format_ts(0, "%Y") == "1970"


def test_parse_range_today(monkeypatch):
    fixed_now = datetime(2023, 1, 2, 15, 30)

    class FixedDatetime(datetime):
        @classmethod
        def now(cls):  # type: ignore[override]
            return fixed_now

    import utils.time as time_utils

    monkeypatch.setattr(time_utils, "datetime", FixedDatetime)
    monkeypatch.setattr(time_utils.time, "time", lambda: fixed_now.timestamp())
    start, end = parse_range("today")
    assert start == int(datetime(2023, 1, 2).timestamp())
    assert end == int(fixed_now.timestamp())


def test_parse_range_invalid(monkeypatch):
    fixed_now_ts = 1_000_000_000
    import utils.time as time_utils

    monkeypatch.setattr(time_utils.time, "time", lambda: fixed_now_ts)
    start, end = parse_range("unknown")
    assert start == fixed_now_ts - 7 * 86400
    assert end == fixed_now_ts
