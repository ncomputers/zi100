from __future__ import annotations

"""Pydantic models for camera configuration."""

import re
from enum import Enum
from typing import Optional

from pydantic import BaseModel, model_validator


class CameraType(str, Enum):
    """Supported camera source types."""

    http = "http"
    rtsp = "rtsp"
    rtmp = "rtmp"
    srt = "srt"
    local = "local"


class Orientation(str, Enum):
    """Image orientation options."""

    horizontal = "horizontal"
    vertical = "vertical"


class Transport(str, Enum):
    """RTSP transport protocols."""

    auto = "auto"
    tcp = "tcp"
    udp = "udp"


class Resolution(str, Enum):
    """Common stream resolutions."""

    original = "original"
    auto = "auto"
    r480p = "480p"
    r720p = "720p"
    r1080p = "1080p"


class Profile(str, Enum):
    """Profile names for multi-stream cameras."""

    main = "main"
    sub = "sub"


class Point(BaseModel):
    """A point on a 2D plane."""

    x: int
    y: int


class CameraBase(BaseModel):
    """Shared attributes for camera schemas."""

    name: Optional[str] = None
    url: Optional[str] = None
    type: Optional[CameraType] = None
    profile: Optional[Profile] = None
    orientation: Optional[Orientation] = None
    transport: Optional[Transport] = None
    resolution: Optional[Resolution | str] = None
    ppe: Optional[bool] = None
    face_recog: Optional[bool] = None
    inout_count: Optional[bool] = None
    reverse: Optional[bool] = None
    show: Optional[bool] = None
    site_id: Optional[int] = None
    line: Optional[list[Point]] = None
    enabled: Optional[bool] = None
    archived: Optional[bool] = None

    class Config:
        validate_by_name = True

    @model_validator(mode="after")
    def _validate(cls, data: "CameraBase") -> "CameraBase":
        url = (data.url or "").lower()
        if url:
            expected: CameraType
            if url.startswith("rtsp://"):
                expected = CameraType.rtsp
            elif url.startswith("http://") or url.startswith("https://"):
                expected = CameraType.http
            elif url.startswith("rtmp://"):
                expected = CameraType.rtmp
            elif url.startswith("srt://"):
                expected = CameraType.srt
            else:
                expected = CameraType.local
            if data.type is None:
                data.type = expected
            elif data.type != expected:
                raise ValueError("url scheme does not match type")

        if data.resolution:
            if (
                isinstance(data.resolution, str)
                and data.resolution not in Resolution._value2member_map_
                and not re.fullmatch(r"\d+x\d+", data.resolution)
            ):
                raise ValueError("invalid resolution")
        if data.name:
            try:
                from routers.cameras import cams, cfg
            except Exception:
                cams, cfg = [], {}
            site_id = (
                data.site_id if data.site_id is not None else cfg.get("site_id", 1)
            )
            for c in cams:
                if c.get("archived"):
                    continue
                if c.get("name") == data.name and c.get("site_id") == site_id:
                    raise ValueError("camera name must be unique per site")
            if data.site_id is None:
                data.site_id = site_id
        return data


class CameraCreate(CameraBase):
    """Schema for creating a camera via the API."""

    name: str
    url: str
    orientation: Orientation = Orientation.vertical
    transport: Transport = Transport.tcp
    resolution: Resolution | str = Resolution.original
    ppe: bool = False
    face_recog: bool = False
    inout_count: bool = False
    reverse: bool = False
    show: bool = False
    enabled: bool = False


class CameraUpdate(CameraBase):
    """Schema for updating a camera via the API."""

    pass
