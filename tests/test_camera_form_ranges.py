from pathlib import Path

from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]


def test_camera_form_has_input_ranges():
    html = (ROOT / "templates" / "cameras.html").read_text()
    soup = BeautifulSoup(html, "html.parser")

    timeout = soup.find("input", {"name": "ready_timeout"})
    frames = soup.find("input", {"name": "ready_frames"})
    duration = soup.find("input", {"name": "ready_duration"})

    assert timeout["min"] == "0"
    assert timeout["max"] == "60"
    assert frames["min"] == "1"
    assert frames["max"] == "1000"
    assert duration["min"] == "0"
    assert duration["max"] == "60"
