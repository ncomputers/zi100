import asyncio
import json
import time
import types

import fakeredis
import pytest

from config import config as cfg
from core import tracker_manager
from modules import gatepass_service, visitor_db
from routers import gatepass
from routers import visitor as visitor_router
from utils.redis import trim_sorted_set


class DummyRequest:
    def __init__(self, query=None):
        self.query_params = query or {}


@pytest.fixture
def redis_client():
    r = fakeredis.FakeRedis(decode_responses=True)
    visitor_db.init_db(r)
    gatepass_service.init(r)
    gatepass.redis = r
    visitor_router.redis = r
    visitor_router.config_obj = {
        "features": {"visitor_mgmt": True},
        "base_url": "http://test",
    }
    gatepass.config_obj = {"features": {"visitor_mgmt": True}}
    return r


def test_gatepass_visitor_flow(redis_client):
    entry = {
        "gate_id": "GPTEST",
        "ts": int(time.time()),
        "name": "Alice",
        "phone": "12345",
        "email": "",
        "host": "Bob",
        "purpose": "Meet",
        "status": "created",
        "valid_to": int(time.time()) + 60,
    }
    gatepass._save_gatepass(entry)
    visitor_db.save_visitor("Alice", "12345")
    result = asyncio.run(visitor_router.invite_lookup("12345"))
    assert result["name"] == "Alice"
    assert result["visits"] == 1


def test_invite_status_flow(redis_client):
    req = DummyRequest()
    resp = asyncio.run(
        visitor_router.invite_create(
            req,
            name="Jane",
            phone="555",
            email="",
            host="Host",
            visit_time="",
            expiry="",
            purpose="Meet",
            photo="",
            send_mail="off",
        )
    )
    iid = resp["id"]
    asyncio.run(visitor_router.invite_approve(iid))
    entries = [json.loads(e) for e in redis_client.zrevrange("invite_records", 0, -1)]
    assert any(
        e["id"] == iid and e["status"] == "accepted_pending_details" for e in entries
    )
    asyncio.run(visitor_router.invite_reject(iid))
    entries = [json.loads(e) for e in redis_client.zrevrange("invite_records", 0, -1)]
    assert any(e["id"] == iid and e["status"] == "rejected" for e in entries)
    count_before = len(entries)
    asyncio.run(visitor_router.invite_delete(iid))
    entries = [json.loads(e) for e in redis_client.zrevrange("invite_records", 0, -1)]
    assert len(entries) == count_before - 1


def test_ppe_log_retention(redis_client, monkeypatch):
    tracker_manager.last_status = None
    redis_client.set(
        "config", json.dumps({"ppe_log_retention_secs": 1, "ppe_log_limit": 10})
    )
    fake_time = types.SimpleNamespace(time=lambda: 1000)
    monkeypatch.setattr(tracker_manager, "time", fake_time)
    tracker_manager.handle_status_change("yellow", redis_client)
    tracker_manager.last_status = None
    fake_time.time = lambda: 2002
    tracker_manager.handle_status_change("red", redis_client)
    logs = redis_client.zrange("ppe_logs", 0, -1)
    assert len(logs) == 1
    log = json.loads(logs[0])
    assert log["status"] == "red_alert"


def test_pubsub_faces_updated(redis_client):
    pubsub = redis_client.pubsub()
    pubsub.subscribe("faces_updated")
    redis_client.publish("faces_updated", "abc")
    message = None
    for _ in range(5):
        message = pubsub.get_message(timeout=0.1)
        if message and message.get("type") == "message":
            break
    assert message and message.get("data") == "abc"


def test_key_naming_ttl_and_pipeline(redis_client):
    entry = {
        "gate_id": "GPKEY",
        "ts": int(time.time()),
        "name": "Key",
        "phone": "1",
        "email": "",
        "host": "",
        "purpose": "",
        "status": "created",
        "valid_to": int(time.time()) + 60,
    }
    gatepass._save_gatepass(entry)
    cache_key = f"gatepass:cache:{entry['gate_id']}"
    assert redis_client.ttl(cache_key) > 0
    pipe = redis_client.pipeline()
    pipe.set("temp:key", "1")
    pipe.expire("temp:key", 10)
    pipe.execute()
    assert redis_client.ttl("temp:key") > 0


def test_face_queue_pipeline_consistency(redis_client):
    fid = "f123"
    data = {"cam_id": "0", "path": "/tmp/a.jpg", "ts": "1"}
    ttl = 300
    pipe = redis_client.pipeline()
    pipe.hset(f"face:raw:{fid}", mapping=data)
    pipe.expire(f"face:raw:{fid}", ttl)
    pipe.rpush("visitor_queue", fid)
    pipe.expire("visitor_queue", ttl)
    pipe.execute()
    fetched_id = redis_client.lpop("visitor_queue")
    assert fetched_id == fid
    assert redis_client.hgetall(f"face:raw:{fetched_id}") == data
