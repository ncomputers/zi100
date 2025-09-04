"""Tests for Redis error handling and logging."""

import sys
from pathlib import Path

import pytest
import redis
from loguru import logger

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from modules import gatepass_service, visitor_db


class FailingRedis:
    def hgetall(self, *args, **kwargs):
        raise redis.RedisError("boom")


class FailingGatepassRedis:
    def zrevrange(self, *args, **kwargs):
        raise redis.RedisError("boom")


def test_get_visitor_by_phone_logs_error(caplog):
    logger.remove()
    logger.add(caplog.handler, level="ERROR")
    visitor_db.init_db(FailingRedis())
    result = visitor_db.get_visitor_by_phone("123")
    assert result is None
    assert "failed to fetch visitor" in caplog.text
    visitor_db._redis = None


def test_update_status_logs_error(caplog):
    logger.remove()
    logger.add(caplog.handler, level="ERROR")
    gatepass_service.init(FailingGatepassRedis())
    with pytest.raises(RuntimeError):
        gatepass_service.update_status("1", "approved")
    assert "failed to fetch gate passes" in caplog.text
    gatepass_service._redis = None
