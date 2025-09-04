from fastapi.testclient import TestClient


def _setup_identity(r, identity_id: str):
    r.hset(
        f"identity:{identity_id}",
        mapping={
            "name": "Bob",
            "company": "Acme",
            "tags": "vip",
            "primary_face_id": "face1",
        },
    )
    r.rpush(f"identity:{identity_id}:faces", "face1", "face2")
    r.hset("identity_face:face1", mapping={"url": "/f1.jpg"})
    r.hset("identity_face:face2", mapping={"url": "/f2.jpg"})
    r.rpush(f"identity:{identity_id}:visits", "2023-01-01", "2023-01-02")
    r.sadd(f"identity:{identity_id}:cameras", "CamA", "CamB")


def test_identity_profile_endpoints(client: TestClient):
    r = client.app.state.redis_client
    identity_id = "id1"
    _setup_identity(r, identity_id)

    resp = client.get(f"/api/identities/{identity_id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == "Bob"
    assert len(data["faces"]) == 2

    resp = client.post(
        f"/api/identities/{identity_id}", json={"name": "Bobby", "tags": ["x"]}
    )
    assert resp.status_code == 200
    assert r.hget(f"identity:{identity_id}", "name") == "Bobby"
    assert r.hget(f"identity:{identity_id}", "tags") == "x"

    resp = client.delete(f"/api/identities/{identity_id}/faces/face2")
    assert resp.status_code == 200
    assert r.lrange(f"identity:{identity_id}:faces", 0, -1) == ["face1"]

    resp = client.post(f"/api/identities/{identity_id}/faces/face1/primary")
    assert resp.status_code == 200
    assert r.hget(f"identity:{identity_id}", "primary_face_id") == "face1"

