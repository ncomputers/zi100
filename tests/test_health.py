from fastapi.testclient import TestClient


def test_live_endpoint_returns_ok(client: TestClient) -> None:
    resp = client.get("/health/live")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_ready_endpoint_behaviour(client: TestClient, monkeypatch) -> None:
    original = client.app.state.ready
    try:
        client.app.state.ready = False
        resp = client.get("/health/ready")
        assert resp.status_code == 503
        client.app.state.ready = True
        # simulate workers ready
        monkeypatch.setattr("routers.health._workers_ready", lambda app: True)
        resp2 = client.get("/health/ready")
        assert resp2.status_code == 200
        assert resp2.json() == {"status": "ok"}
    finally:
        client.app.state.ready = original
