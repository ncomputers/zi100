"""Tests for navigation links rendering."""

import copy

from bs4 import BeautifulSoup


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
