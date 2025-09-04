"""Tests for profile photo processing."""

import io
from pathlib import Path

from PIL import Image

import routers.profile as profile


def test_profile_photo_processing(client):
    img = Image.new("RGB", (512, 512), color="red")
    exif = Image.Exif()
    exif[0x010F] = "camera"
    buf = io.BytesIO()
    img.save(buf, format="JPEG", exif=exif)
    buf.seek(0)
    files = {"photo": ("pic.jpg", buf, "image/jpeg")}
    resp = client.post("/profile", data={"name": "tester"}, files=files)
    assert resp.status_code == 200
    assert resp.json()["saved"] is True
    assert "profile_photo" in profile.cfg
    path = Path(
        profile.BASE_DIR / profile.cfg["profile_photo"].split("?")[0].lstrip("/")
    )
    assert path.exists()
    saved = Image.open(path)
    assert saved.size == (256, 256)
    assert not saved.getexif()
    resp = client.post("/profile", data={"name": "tester", "remove_photo": "1"})
    assert resp.status_code == 200
    assert resp.json()["saved"] is True
    assert "profile_photo" not in profile.cfg
    assert not path.exists()
