"""Tests for navigation links rendering."""

import copy

from bs4 import BeautifulSoup


def test_vms_links_hidden_without_license(client):
    """VMS navigation links should be absent when license lacks visitor management."""

    from config import config as cfg

    orig = copy.deepcopy(cfg.get("license_info", {}))
    try:
        cfg.setdefault("features", {})["visitor_mgmt"] = True
        cfg["license_info"] = {"features": {"visitor_mgmt": False}}
        resp = client.get("/settings")
        assert resp.status_code == 200
        html = resp.text
        assert "/vms" not in html
        assert "/manage_faces" not in html
        assert "/visitor_report" not in html
        assert "/invite" not in html
    finally:
        cfg["license_info"] = orig
        client.post("/login", data={"username": "admin", "password": "rapidadmin"})


def test_invite_link_present_with_license(client):
    """Invite link should appear when visitor management is licensed."""

    resp = client.get("/settings")
    assert resp.status_code == 200
    html = resp.text
    assert "/invite" in html


def test_nav_ul_responsive_without_nowrap(client):
    """Navbar list should rely on CSS for wrapping and omit inline nowrap style."""
    resp = client.get("/settings")
    assert resp.status_code == 200
    soup = BeautifulSoup(resp.text, "html.parser")
    ul = soup.select_one("#mainNav ul.navbar-nav")
    assert ul is not None
    classes = ul.get("class", [])
    assert "flex-lg-row" in classes
    assert "d-none" not in classes and "d-lg-flex" not in classes
    assert "white-space: nowrap" not in (ul.get("style") or "")
