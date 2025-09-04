"""Dependency providers for shared application state."""

from __future__ import annotations

from typing import TYPE_CHECKING, Dict, List

import redis.asyncio as redis
from fastapi import Request, WebSocket
from fastapi.templating import Jinja2Templates
from redis import Redis

from modules.tracker import PersonTracker

if TYPE_CHECKING:
    # Provide accurate type hints while keeping runtime annotations simple
    RequestOrWebSocket = Request | WebSocket
else:
    RequestOrWebSocket = Request


def get_settings(request: RequestOrWebSocket) -> dict:
    return request.app.state.config


def get_trackers(request: RequestOrWebSocket) -> Dict[int, PersonTracker]:
    return request.app.state.trackers


def get_cameras(request: RequestOrWebSocket) -> List[dict]:
    cams = request.app.state.cameras
    include = False
    if isinstance(request, Request) and request.query_params.get("include_archived"):
        include = True
    if include:
        return cams
    return [c for c in cams if not c.get("archived")]


def get_redis(request: RequestOrWebSocket) -> redis.Redis:

    return request.app.state.redis_client


def get_templates(request: RequestOrWebSocket) -> Jinja2Templates:
    return request.app.state.templates


def get_config_path(request: RequestOrWebSocket) -> str:
    return request.app.state.config_path
