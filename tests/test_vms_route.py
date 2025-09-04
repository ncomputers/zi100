"""Ensure VMS dashboard endpoint responds."""


def test_vms_route(client):
    from config import config as cfg

    cfg.setdefault("features", {})["visitor_mgmt"] = True
    resp = client.get("/vms")
    assert resp.status_code == 200
    assert "Visitor Management" in resp.text
