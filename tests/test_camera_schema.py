import pytest
from pydantic import ValidationError

from schemas.camera import CameraCreate, CameraType, CameraUpdate, Orientation, Point


def test_url_type_validation():
    cam = CameraCreate(name="c1", url="rtsp://example")
    assert cam.type == CameraType.rtsp
    with pytest.raises(ValidationError):
        CameraCreate(name="c2", url="http://example", type=CameraType.rtsp)


def test_line_optional_for_counting():
    cam = CameraCreate(name="c1", url="rtsp://a", inout_count=True)
    assert cam.line is None

    cam = CameraCreate(
        name="c1",
        url="rtsp://a",
        inout_count=True,
        line=[Point(x=1, y=2), Point(x=3, y=4)],
    )
    assert len(cam.line) == 2


def test_site_id_defaults(monkeypatch):
    import routers.cameras as rc

    rc.cams = []
    monkeypatch.setattr(rc, "cfg", {}, raising=False)
    cam = CameraCreate(name="c1", url="rtsp://a")
    assert cam.site_id == 1


def test_unique_name_per_site(monkeypatch):
    import routers.cameras as rc

    rc.cams = [{"name": "CamX", "site_id": 1}]
    with pytest.raises(ValidationError):
        CameraCreate(name="CamX", url="rtsp://a", site_id=1)


def test_update_uses_same_validation():
    assert CameraUpdate(
        name="u1",
        url="rtsp://a",
        inout_count=True,
        line=[Point(x=1, y=2)],
    )
    assert CameraUpdate(
        name="u1",
        url="rtsp://a",
        inout_count=True,
        line=[Point(x=1, y=2), Point(x=3, y=4)],
    )


def test_camera_happy_path():
    cam = CameraCreate(
        name="ok", url="rtsp://a", line=[Point(x=0, y=0), Point(x=1, y=1)]
    )
    assert cam.orientation is Orientation.vertical
    assert cam.type == CameraType.rtsp


def test_bad_url_raises_error():
    with pytest.raises(ValidationError):
        CameraCreate(name="c1", url="ftp://bad", type=CameraType.rtsp)


def test_invalid_orientation_enum():
    with pytest.raises(ValidationError):
        CameraCreate(name="c1", url="rtsp://a", orientation="sideways")
