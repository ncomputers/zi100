"""Tests for feedback submission and file validation."""

from pathlib import Path

import fakeredis
import pytest
from fastapi import FastAPI
from fastapi.templating import Jinja2Templates
from fastapi.testclient import TestClient

from routers.feedback import router


@pytest.fixture()
def client():
    app = FastAPI()
    app.state.config = {}
    app.state.redis_client = fakeredis.FakeRedis(decode_responses=True)
    app.state.templates = Jinja2Templates(
        directory=str(Path(__file__).resolve().parents[1] / "templates")
    )
    app.include_router(router)
    with TestClient(app) as c:
        yield c


def _base_data():
    return {
        "title": "test",
        "description": "test",
        "type": "issue",
        "severity": "high",
        "module": "Dashboard",
        "repro": "Always",
    }


def test_submit_feedback_accepts_valid_image(client):
    data = {**_base_data(), "contact": "user@example.com"}
    files = [("attachments", ("test.png", b"img", "image/png"))]
    resp = client.post("/feedback", data=data, files=files)
    assert resp.status_code == 200
    assert "id" in resp.json()


def test_submit_feedback_rejects_non_image(client):
    data = _base_data()
    files = [("attachments", ("test.txt", b"text", "text/plain"))]
    resp = client.post("/feedback", data=data, files=files)
    assert resp.status_code == 400


def test_submit_feedback_rejects_large_file(client):
    big = b"0" * (5 * 1024 * 1024 + 1)
    data = _base_data()
    files = [("attachments", ("big.png", big, "image/png"))]
    resp = client.post("/feedback", data=data, files=files)
    assert resp.status_code == 400
