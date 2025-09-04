import pathlib
import sys

sys.path.append(str(pathlib.Path(__file__).resolve().parents[1]))

from fastapi import FastAPI
from fastapi.testclient import TestClient

from routers import api_alerts


class DummyRedis:
    def lrange(self, key, start, end):
        return [b'{"message":"hi"}', b"plain"]


def create_app():
    app = FastAPI()
    app.state.redis_client = DummyRedis()
    app.include_router(api_alerts.router)
    return app


def test_recent_alerts():
    app = create_app()
    client = TestClient(app)
    r = client.get("/api/alerts/recent")
    assert r.status_code == 200
    assert r.json() == [{"message": "hi"}, "plain"]
