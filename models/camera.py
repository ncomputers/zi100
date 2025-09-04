"""Camera persistence helpers using Redis."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Optional

from utils.redis import get_sync_client


class CameraProfile(str, Enum):
    main = "main"
    sub = "sub"


class Orientation(str, Enum):
    horizontal = "horizontal"
    vertical = "vertical"


class Transport(str, Enum):
    auto = "auto"
    tcp = "tcp"
    udp = "udp"


@dataclass
class Camera:
    id: str
    name: str
    type: str
    url: str
    analytics: dict[str, bool] = field(default_factory=dict)
    line: Optional[list[int]] = None
    orientation: Orientation = Orientation.vertical
    transport: Transport = Transport.tcp
    resolution: Optional[str] = None
    reverse: bool = False
    show: bool = False
    profile: Optional[CameraProfile] = None
    site_id: Optional[str] = None
    enabled: bool = True
    archived: bool = False
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)


def _serialize(cam: Camera) -> dict[str, Any]:
    return {
        "id": cam.id,
        "name": cam.name,
        "type": cam.type,
        "url": cam.url,
        "analytics": cam.analytics,
        "line": cam.line,
        "orientation": cam.orientation.value,
        "transport": cam.transport.value,
        "resolution": cam.resolution,
        "reverse": cam.reverse,
        "show": cam.show,
        "profile": cam.profile.value if cam.profile else None,
        "site_id": cam.site_id,
        "enabled": cam.enabled,
        "archived": cam.archived,
        "created_at": cam.created_at.isoformat(),
        "updated_at": cam.updated_at.isoformat(),
    }


def _deserialize(data: dict[str, Any]) -> Camera:
    return Camera(
        id=data["id"],
        name=data["name"],
        type=data["type"],
        url=data["url"],
        analytics=data.get("analytics") or {},
        line=data.get("line"),
        orientation=Orientation(data["orientation"]),
        transport=Transport(data["transport"]),
        resolution=data.get("resolution"),
        reverse=data.get("reverse", False),
        show=data.get("show", False),
        profile=CameraProfile(data["profile"]) if data.get("profile") else None,
        site_id=data.get("site_id"),
        enabled=data.get("enabled", True),
        archived=data.get("archived", False),
        created_at=datetime.fromisoformat(data["created_at"]),
        updated_at=datetime.fromisoformat(data["updated_at"]),
    )


def _key(cam_id: str) -> str:
    return f"camera:{cam_id}"


def create_camera(cam: Camera, client=None) -> None:
    client = client or get_sync_client()
    client.set(_key(cam.id), json.dumps(_serialize(cam)))


def get_camera(cam_id: str, client=None) -> Optional[Camera]:
    client = client or get_sync_client()
    data = client.get(_key(cam_id))
    if not data:
        return None
    return _deserialize(json.loads(data))


def update_camera(cam: Camera, client=None) -> None:
    client = client or get_sync_client()
    if not client.exists(_key(cam.id)):
        return
    client.set(_key(cam.id), json.dumps(_serialize(cam)))


def delete_camera(cam_id: str, client=None) -> None:
    client = client or get_sync_client()
    client.delete(_key(cam_id))
