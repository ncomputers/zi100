import base64
import os
from pathlib import Path

from fastapi.responses import FileResponse

from config import config as cfg
from modules import gatepass_service
from modules.export import EXPORT_DIR, export_pdf


def test_export_pdf_resolves_root_relative_urls(caplog):
    css_path = Path("static/test.css")
    css_path.write_text("body { color: red; }")
    html = (
        "<html><head><link rel='stylesheet' href='/static/test.css'></head>"
        "<body><p>Hello</p></body></html>"
    )
    filename = "test_static_url"
    caplog.set_level("ERROR")
    response = export_pdf(html, filename)
    assert isinstance(response, FileResponse)
    pdf_path = EXPORT_DIR / f"{filename}.pdf"
    assert pdf_path.exists()
    assert "URLError" not in caplog.text
    pdf_path.unlink()
    css_path.unlink()


def test_export_pdf_independent_of_cwd(tmp_path, caplog):
    css_path = Path("static/test2.css").resolve()
    css_path.write_text("body { color: blue; }")
    html = (
        "<html><head><link rel='stylesheet' href='/static/test2.css'></head>"
        "<body><p>Hi</p></body></html>"
    )
    orig = Path.cwd()
    caplog.set_level("ERROR")
    try:
        os.chdir(tmp_path)
        response = export_pdf(html, "cwd_test")
    finally:
        os.chdir(orig)
    assert isinstance(response, FileResponse)
    pdf_path = EXPORT_DIR / "cwd_test.pdf"
    assert pdf_path.exists()
    assert "URLError" not in caplog.text
    pdf_path.unlink()
    css_path.unlink()


def test_export_pdf_includes_gatepass_assets(monkeypatch):
    png_bytes = base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMB/6X2v4QAAAAASUVORK5CYII="
    )
    sig = Path("static/signatures/test_sig.png")
    sig.parent.mkdir(parents=True, exist_ok=True)
    sig.write_bytes(png_bytes)
    monkeypatch.setitem(
        cfg,
        "branding",
        {"company_logo_url": "static/logo1.png", "footer_logo_url": "static/logo2.png"},
    )
    rec = {"status": "approved", "signature": "static/signatures/test_sig.png"}
    html = gatepass_service.render_gatepass_card(rec, "/static/logo1.png")
    full_html = (
        "<html><head><link rel='stylesheet' href='/static/css/gatepass.css'></head>"
        f"<body>{html}</body></html>"
    )
    response = export_pdf(full_html, "gatepass_assets")
    assert isinstance(response, FileResponse)
    pdf_path = EXPORT_DIR / "gatepass_assets.pdf"
    data = pdf_path.read_bytes()
    assert data.count(b"/Image") >= 2
    pdf_path.unlink()
    sig.unlink()
