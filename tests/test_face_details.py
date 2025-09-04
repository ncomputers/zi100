"""Tests for visitor face_details endpoint."""

import fakeredis
from fastapi import FastAPI
from fastapi.testclient import TestClient

import modules.utils as utils
from routers import visitor


def test_face_details_returns_metadata(monkeypatch, tmp_path):
    cfg = {
        "features": {"visitor_mgmt": True, "face_recognition": True},
        "visitor_model": "buffalo_l",
    }
    r = fakeredis.FakeRedis()
    visitor.init_context(cfg, r, str(tmp_path), [])
    monkeypatch.setattr(
        utils, "require_roles", lambda request, roles: {"role": "admin"}
    )

    face_id = "1" * 32
    created_at = 1609459200
    r.hset(
        f"face:known:{face_id}",
        mapping={
            "name": "Alice",
            "gate_pass_id": "GP1",
            "visitor_type": "Official",
            "created_at": str(created_at),
            "confidence": "0.9",
        },
    )
    app = FastAPI()
    app.include_router(visitor.router)
    client = TestClient(app)
    resp = client.get(f"/face_details/{face_id}")
    assert resp.status_code == 200
    assert resp.json() == {
        "name": "Alice",
        "gate_pass_id": "GP1",
        "visitor_type": "Official",
        "date": "01-Jan-2021",
        "confidence": 0.9,
        "model_version": "",
        "embedding_version": "",
        "ids": [face_id],
        "images": [],
    }


def test_face_details_includes_visitor_id(monkeypatch, tmp_path):
    cfg = {
        "features": {"visitor_mgmt": True, "face_recognition": True},
        "visitor_model": "buffalo_l",
    }
    r = fakeredis.FakeRedis()
    visitor.init_context(cfg, r, str(tmp_path), [])
    monkeypatch.setattr(
        utils, "require_roles", lambda request, roles: {"role": "admin"}
    )

    face_id = "2" * 32
    created_at = 1609459200
    r.hset(
        f"face:known:{face_id}",
        mapping={
            "name": "Bob",
            "gate_pass_id": "GP2",
            "visitor_type": "Contractor",
            "created_at": str(created_at),
            "confidence": "0.8",
            "visitor_id": "VID123",
        },
    )
    app = FastAPI()
    app.include_router(visitor.router)
    client = TestClient(app)
    resp = client.get(f"/face_details/{face_id}")
    assert resp.status_code == 200
    assert resp.json() == {
        "name": "Bob",
        "gate_pass_id": "GP2",
        "visitor_type": "Contractor",
        "date": "01-Jan-2021",
        "confidence": 0.8,
        "model_version": "",
        "embedding_version": "",
        "ids": [face_id],
        "images": [],
        "visitor_id": "VID123",
    }


def test_face_details_rejects_invalid_id(monkeypatch, tmp_path):
    cfg = {
        "features": {"visitor_mgmt": True, "face_recognition": True},
        "visitor_model": "buffalo_l",
    }
    r = fakeredis.FakeRedis()
    visitor.init_context(cfg, r, str(tmp_path), [])
    monkeypatch.setattr(
        utils, "require_roles", lambda request, roles: {"role": "admin"}
    )
    app = FastAPI()
    app.include_router(visitor.router)
    client = TestClient(app)
    resp = client.get("/face_details/invalid!id")
    assert resp.status_code == 400
