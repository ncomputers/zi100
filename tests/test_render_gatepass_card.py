from pathlib import Path

from bs4 import BeautifulSoup

from config import config as cfg
from modules import gatepass_service


def test_render_gatepass_card_handles_missing_logo(monkeypatch):
    monkeypatch.setitem(cfg, "branding", {"company_logo_url": "/missing.png"})
    monkeypatch.setitem(cfg, "logo_url", "")
    monkeypatch.setitem(cfg, "logo2_url", "")
    html = gatepass_service.render_gatepass_card({"status": "approved"})
    assert "/missing.png" not in html
    assert "bi bi-person" in html
    assert "QR unavailable" in html


def test_render_gatepass_card_prefixes_paths(monkeypatch):
    sig = Path("static/signatures/test_sig.png")
    sig.parent.mkdir(parents=True, exist_ok=True)
    sig.write_bytes(b"data")
    monkeypatch.setitem(
        cfg,
        "branding",
        {"company_logo_url": "static/logo1.png", "footer_logo_url": "static/logo2.png"},
    )
    rec = {"status": "approved", "signature": "static/signatures/test_sig.png"}
    html = gatepass_service.render_gatepass_card(rec)
    assert "src='/static/logo1.png'" in html
    assert "src='/static/logo2.png'" in html
    assert "src='/static/signatures/test_sig.png'" in html
    sig.unlink()


def test_render_gatepass_card_defaults_dash():
    html = gatepass_service.render_gatepass_card({})
    soup = BeautifulSoup(html, "html.parser")
    assert soup.select_one("#pEmail").text.strip() == "—"
    assert soup.select_one("#pType").text.strip() == "—"
    assert soup.select_one("#pCompany").text.strip() == "—"
    assert soup.select_one("#pValid").text.strip() == "—"
