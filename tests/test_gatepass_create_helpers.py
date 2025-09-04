"""Tests for gatepass creation helper functions."""

import asyncio
import base64
import io
import json
import time

import pytest
from starlette.datastructures import UploadFile

from routers.gatepass import create


class FakeRedis:
    """Minimal fake Redis implementation for helper tests."""

    def __init__(self):
        self.store: dict[str, dict[str, str]] = {}

    def hget(self, name: str, key: str):
        return self.store.get(name, {}).get(key)

    def hset(self, name: str, mapping: dict[str, str]):
        self.store.setdefault(name, {}).update(mapping)

    def hgetall(self, name: str):
        return {k.encode(): v.encode() for k, v in self.store.get(name, {}).items()}

    def hdel(self, name: str, *keys: str):
        for key in keys:
            self.store.get(name, {}).pop(key, None)


def test_extract_photo_from_captured():
    data = b"testimage"
    captured = "data:image/jpeg;base64," + base64.b64encode(data).decode()
    res = asyncio.run(create._extract_photo(None, captured))
    assert res == data


def test_extract_photo_from_upload():
    data = b"fileimage"
    upload = UploadFile(filename="x.jpg", file=io.BytesIO(data))
    res = asyncio.run(create._extract_photo(upload, ""))
    assert res == data


def test_merge_invite_fields(monkeypatch):
    fake = FakeRedis()
    fake.hset(
        "invite:ABC",
        {
            "name": "Invited",
            "phone": "123",
            "email": "i@example.com",
            "host": "Host",
            "purpose": "Meet",
            "visitor_type": "VIP",
            "company": "Acme",
            "expiry": "2025-01-01T00:00:00",
        },
    )
    monkeypatch.setattr(create, "redis", fake)
    data = {
        "name": "",
        "phone": "",
        "email": "",
        "host": "",
        "purpose": "",
        "visitor_type": "",
        "company_name": "",
        "valid_to": "",
    }
    merged = create._merge_invite_fields(data, "ABC")
    assert merged["name"] == "Invited"
    assert merged["company_name"] == "Acme"
    assert merged["valid_to"] == "2025-01-01T00:00:00"


def test_validate_active_pass_active_exists():
    fake = FakeRedis()
    ts_future = int(time.time()) + 60
    fake.hset("gatepass:active_phone", {"123": "GP1"})
    fake.hset(
        "gatepass:active",
        {"GP1": json.dumps({"status": "approved", "valid_to": ts_future})},
    )
    with pytest.raises(ValueError):
        create._validate_active_pass(fake, "123")


def test_validate_active_pass_cleanup():
    fake = FakeRedis()
    ts_past = int(time.time()) - 60
    fake.hset("gatepass:active_phone", {"123": "GP1"})
    fake.hset(
        "gatepass:active",
        {"GP1": json.dumps({"status": "approved", "valid_to": ts_past})},
    )
    create._validate_active_pass(fake, "123")
    assert not fake.hget("gatepass:active_phone", "123")
    assert not fake.hget("gatepass:active", "GP1")


def test_validate_active_pass_redis_error():
    class ErrorRedis(FakeRedis):
        def hget(self, name: str, key: str):  # type: ignore[override]
            raise RuntimeError("boom")

    err = ErrorRedis()
    with pytest.raises(RuntimeError):
        create._validate_active_pass(err, "123")
