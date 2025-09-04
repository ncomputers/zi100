"""Ensure gatepass templates compile without syntax errors."""

from pathlib import Path

from jinja2 import Environment, FileSystemLoader


def test_gatepass_templates_compile(tmp_path):
    env = Environment(loader=FileSystemLoader("templates"))
    env.get_template("gatepass_view.html")
    env.get_template("gatepass_print.html")
    env.get_template("gatepass_card.html")


def test_gatepass_templates_share_styles():
    view_src = Path("templates/gatepass_view.html").read_text().lower()
    print_src = Path("templates/gatepass_print.html").read_text().lower()
    assert "css/gatepass.css" in view_src
    assert "css/gatepass.css" in print_src
    assert "bootswatch" not in view_src
