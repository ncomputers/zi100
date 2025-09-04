"""Tests for gatepass time formatting helper."""

import sys
import time
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from routers import gatepass


@pytest.mark.parametrize(
    "valid_from, valid_to",
    [
        (None, None),
        (2000, None),
        (None, 3000),
        (2000, 3000),
    ],
)
def test_format_gatepass_times(valid_from, valid_to):
    data = {"ts": "1000"}
    if valid_from is not None:
        data["valid_from"] = str(valid_from)
    if valid_to is not None:
        data["valid_to"] = str(valid_to)

    gatepass._format_gatepass_times(data)

    assert data["time"] == time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(1000))
    if valid_from is not None:
        assert data["valid_from_str"] == time.strftime(
            "%Y-%m-%d %H:%M:%S", time.localtime(valid_from)
        )
    else:
        assert "valid_from_str" not in data
    if valid_to is not None:
        assert data["valid_to_str"] == time.strftime(
            "%Y-%m-%d %H:%M:%S", time.localtime(valid_to)
        )
    else:
        assert "valid_to_str" not in data

