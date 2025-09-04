"""Visitor management helpers and router aggregation."""

from __future__ import annotations

import base64
import json
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from fastapi import APIRouter
from fastapi.templating import Jinja2Templates
from loguru import logger

from config import config
from modules import face_db, visitor_db
from utils.redis import trim_sorted_set

from .face_loader import load_faces

# Proxies for shared context attributes
redis = None
templates = None
config_obj: dict[str, Any] = {}
cam_list: list = []

# Shared context populated via ``init_context``
_ctx = SimpleNamespace(config={}, redis=None, templates=None, cam_list=[])
face_app = None
_face_search_enabled = False
require_roles = None


def get_context() -> SimpleNamespace:
    """Return shared visitor context for dependency injection.

    The context may be partially initialised in tests that set module-level
    globals directly without calling :func:`init_context`. Synchronise the
    stored namespace with any such globals before returning it.
    """
    if redis is not None and _ctx.redis is not redis:
        _ctx.redis = redis
    if config_obj and _ctx.config is not config_obj:
        _ctx.config = config_obj
    if templates is not None and _ctx.templates is not templates:
        _ctx.templates = templates
    return _ctx


# ---------------------------------------------------------------------------
# helper functions for master records
# ---------------------------------------------------------------------------
def _save_visitor_master(
    name: str,
    email: str = "",
    phone: str = "",
    visitor_type: str = "",
    company_name: str = "",
    photo_url: str = "",
) -> str:
    """Persist visitor info and return visitor_id."""
    if not phone:
        raise ValueError("phone required")
    try:
        data = json.dumps(
            {
                "email": email,
                "phone": phone,
                "visitor_type": visitor_type,
                "company": company_name,
                "photo_url": photo_url,
            }
        )
        redis_client = getattr(visitor_db, "_redis", None) or _ctx.redis
        if not redis_client:
            raise RuntimeError("redis not initialized")
        redis_client.hset("visitor:master", name, data)
        vid = visitor_db.get_or_create_visitor(
            name, phone, email, company_name, photo_url
        )
        return vid
    except Exception as exc:  # pragma: no cover - defensive
        logger.exception("failed to save visitor master {}: {}", name, exc)
        raise RuntimeError("failed to save visitor master") from exc


# _save_host_master routine


def _save_host_master(host: str, email: str = "") -> None:
    host = host or config.get("default_host", "")
    if not host:
        raise ValueError("host required")
    try:
        data = json.dumps({"email": email})
        _ctx.redis.hset("host_master", host, data)
        visitor_db.save_host(host, email)
        invalidate_host_cache()
    except Exception as exc:  # pragma: no cover - defensive
        logger.exception("failed to save host master {}: {}", host, exc)
        raise RuntimeError("failed to save host master") from exc


# ---------------------------------------------------------------------------
# host cache helpers
# ---------------------------------------------------------------------------
_HOST_CACHE_KEY = "host_cache"
_HOST_CACHE_TTL_SECS = 5 * 60


def get_host_names_cached() -> list[str]:
    cached = _ctx.redis.get(_HOST_CACHE_KEY)
    if cached:
        try:
            return json.loads(cached if isinstance(cached, str) else cached.decode())
        except Exception:
            _ctx.redis.delete(_HOST_CACHE_KEY)
    host_map = {
        k.decode() if isinstance(k, bytes) else k: (
            json.loads(v) if isinstance(v, (bytes, str)) else v
        )
        for k, v in _ctx.redis.hgetall("host_master").items()
    }
    names = list(host_map.keys())
    _ctx.redis.set(_HOST_CACHE_KEY, json.dumps(names), ex=_HOST_CACHE_TTL_SECS)
    return names


def invalidate_host_cache() -> None:
    _ctx.redis.delete(_HOST_CACHE_KEY)


# ---------------------------------------------------------------------------
# face utilities
# ---------------------------------------------------------------------------


def _load_known_faces(
    limit: int = 50,
    cursor: int | None = None,
    q: str | None = None,
    camera_id: str | None = None,
    last_seen_after: int | None = None,
) -> tuple[list[dict], int | None]:
    fields_map = {
        "prefix": "face:known:",
        "fields": {
            "id": lambda fid, f, ts, d, img: fid,
            "name": lambda fid, f, ts, d, img: f.get("name", ""),
            "image": lambda fid, f, ts, d, img: img,
            "gate_pass_id": lambda fid, f, ts, d, img: f.get("gate_pass_id", fid),
            "visitor_type": lambda fid, f, ts, d, img: f.get("visitor_type", ""),
            "date": lambda fid, f, ts, d, img: d,
            "confidence": lambda fid, f, ts, d, img: float(f.get("confidence") or 0.0),
            "camera_id": lambda fid, f, ts, d, img: f.get("camera_id", ""),
            "device_id": lambda fid, f, ts, d, img: f.get("device_id", ""),
            "source_platform": lambda fid, f, ts, d, img: f.get("source_platform", ""),
        },
    }
    return load_faces(
        "face:known_ids",
        fields_map,
        limit=limit,
        cursor=cursor,
        q=q,
        camera_id=camera_id,
        last_seen_after=last_seen_after,
    )


def _load_unregistered_faces(
    limit: int = 50,
    cursor: int | None = None,
    q: str | None = None,
    camera_id: str | None = None,
    last_seen_after: int | None = None,
) -> tuple[list[dict], int | None]:
    fields_map = {
        "prefix": "face:unregistered:",
        "fields": {
            "face_id": lambda fid, f, ts, d, img: fid,
            "image": lambda fid, f, ts, d, img: img,
            "name": lambda fid, f, ts, d, img: f.get("name", ""),
        },
    }
    return load_faces(
        "face:unregistered_ids",
        fields_map,
        limit=limit,
        cursor=cursor,
        q=q,
        camera_id=camera_id,
        last_seen_after=last_seen_after,
    )


# ---------------------------------------------------------------------------
# initialization and helpers
# ---------------------------------------------------------------------------
VISITOR_LOG_RETENTION_SECS = int(config.get("log_retention_days", 30)) * 24 * 60 * 60


async def _trim_visitor_logs() -> None:
    now = int(time.time())
    await trim_sorted_set(_ctx.redis, "visitor_logs", now, VISITOR_LOG_RETENTION_SECS)
    _ctx.redis.expire("visitor_logs", VISITOR_LOG_RETENTION_SECS)


def init_context(
    cfg: dict, redis_client, templates_path: str, cameras: list | None = None
):
    """Initialise module level state."""

    global face_app, _face_search_enabled

    # mutate config in-place so submodules importing it receive updated values
    _ctx.config.clear()
    _ctx.config.update(cfg)

    _ctx.redis = redis_client
    _ctx.templates = Jinja2Templates(directory=templates_path)
    _ctx.cam_list = cameras or []
    global redis, templates, config_obj, cam_list
    redis = _ctx.redis
    templates = _ctx.templates
    cam_list = _ctx.cam_list
    config_obj = _ctx.config

    # ensure submodules referencing ``get_context`` receive updated state
    try:
        from . import faces as _faces
        from . import visit_requests as _visit_requests

        _faces.ctx = _ctx
        _faces.redis = _ctx.redis
        _faces.templates = _ctx.templates

        _visit_requests.ctx = _ctx
        _visit_requests.redis = _ctx.redis
        _visit_requests.templates = _ctx.templates
    except Exception:
        pass

    face_app = None

    visitor_db.init_db(redis_client)
    try:  # pragma: no cover - init failures
        face_db.init(cfg, redis_client)
        face_app = face_db.face_app
        _face_search_enabled = True
    except Exception as exc:  # pragma: no cover - init failures
        _face_search_enabled = False
        face_app = None
        logger.warning("face_db init failed: {}", exc)


def _search_embeddings(
    img_bytes: bytes | None, top_n: int, threshold: float | None = None
) -> list[dict]:
    """Return top matches for provided image bytes."""
    if not img_bytes or not _face_search_enabled:
        return []
    try:
        matches = face_db.search_faces(img_bytes, top_n, threshold)
        results: list[dict] = []
        for m in matches:
            raw_id = m.get("id", "")
            visitor_id = raw_id.split(":", 1)[-1]
            data = {
                k.decode() if isinstance(k, bytes) else k: (
                    v.decode() if isinstance(v, bytes) else v
                )
                for k, v in _ctx.redis.hgetall(f"face:known:{visitor_id}").items()
            }
            if not data:
                continue
            img_b64 = data.get("image") or data.get("image_b64", "")
            img_path = data.get("image_path")
            if not img_b64 and img_path and Path(img_path).exists():
                with open(img_path, "rb") as f:
                    img_b64 = base64.b64encode(f.read()).decode()
            results.append(
                {
                    "id": visitor_id,
                    "name": data.get("name", ""),
                    "image": img_b64,
                    "score": m.get("score", 0.0),
                }
            )
        return results
    except Exception as exc:  # pragma: no cover - search errors
        logger.exception("face search failed: {}", exc)
        return []


# ---------------------------------------------------------------------------
# Aggregate routers from submodules
# ---------------------------------------------------------------------------
router = APIRouter()

from . import faces, invites, registration, visit_requests  # noqa: E402

# Re-export invite creation helper for external access/tests
from .invites import (  # noqa: F401
    invite_approve,
    invite_complete_submit,
    invite_create,
    invite_get,
    invite_list,
    invite_lookup,
    invite_public_form,
    invite_public_submit,
)
from .registration import custom_report  # noqa: F401

router.include_router(registration.router)
router.include_router(faces.router)
router.include_router(invites.router)
router.include_router(visit_requests.router)

__all__ = [
    "router",
    "init_context",
    "get_host_names_cached",
    "invalidate_host_cache",
    "_save_visitor_master",
    "_save_host_master",
    "VISITOR_LOG_RETENTION_SECS",
    "_trim_visitor_logs",
    "_search_embeddings",
    "get_context",
    "face_app",
    "invite_create",
    "invite_list",
    "invite_lookup",
    "invite_get",
    "invite_public_form",
    "invite_public_submit",
    "invite_complete_submit",
    "invite_approve",
    "custom_report",
]
