"""Tests for settings template partials rendering."""


def test_settings_partials_render(client):
    """Settings page should include all accordion sections from partials."""
    resp = client.get("/settings")
    assert resp.status_code == 200
    html = resp.text
    for heading in [
        "System Configuration",
        "Detection Settings",
        "Alert Settings",
        "Visitor Management",
        "Face Recognition",
        "Display Preferences",
        "Branding",
        "License",
    ]:
        assert heading in html
