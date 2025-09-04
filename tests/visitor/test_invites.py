def test_invite_panel_accessible_for_viewer(client):
    client.post("/login", data={"username": "viewer", "password": "viewer"})
    resp = client.get("/invite")
    assert resp.status_code == 200
