from fastapi.testclient import TestClient


def test_activity_pagination(client: TestClient):
    r = client.app.state.redis_client
    r.xadd("activity:decisions", {"value": "a"}, id="1-0")
    r.xadd("activity:decisions", {"value": "b"}, id="2-0")
    r.xadd("activity:decisions", {"value": "c"}, id="3-0")

    resp = client.get("/api/activity?limit=2")
    assert resp.status_code == 200
    data = resp.json()
    assert [i["value"] for i in data["items"]] == ["c", "b"]
    cursor = data["next"]

    resp2 = client.get(f"/api/activity?limit=2&cursor={cursor}")
    assert resp2.status_code == 200
    data2 = resp2.json()
    assert [i["value"] for i in data2["items"]] == ["a"]
