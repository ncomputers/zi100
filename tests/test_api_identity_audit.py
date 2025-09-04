from fastapi.testclient import TestClient


def test_identity_audit_logged(client: TestClient):
    r = client.app.state.redis_client
    resp = client.post(
        "/api/identities/attach", data={"face_id": "f1", "identity_id": "i1"}
    )
    assert resp.status_code == 200
    entries = r.xrevrange("audit:identities", max="+", min="-", count=1)
    assert entries
    _id, fields = entries[0]
    assert fields["action"] == "attach"
    assert fields["face_id"] == "f1"
    assert fields["identity_id"] == "i1"
