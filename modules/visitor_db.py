"""Simple Redis helper for frequent visitors and hosts."""

from __future__ import annotations

"""Redis helpers for visitor data.

Keys follow a ``<domain>:<entity>:<id>`` naming convention using the
``visitor`` namespace.
"""

import json
import time
from itertools import islice
from typing import Dict, Iterator, Optional

import redis
from loguru import logger

from utils.ids import generate_id

_redis: Optional[redis.Redis] = None

MASTER_KEY = "visitor:master"


# init_db routine
def init_db(redis_client: redis.Redis) -> None:
    """Initialize Redis client for visitor storage."""
    global _redis
    _redis = redis_client


# save_visitor routine
def save_visitor(
    name: str,
    phone: str,
    email: str = "",
    org: str = "",
    photo: str = "",
    visitor_id: str | None = None,
) -> str:
    """Save visitor info and return a persistent visitor_id."""
    if not _redis or not phone:
        raise ValueError("Redis not initialized or phone missing")
    try:
        existing = _fetch_visitor_record(phone)
        vid = visitor_id or existing.get("id") or generate_id()
        mapping = {"id": vid, "name": name, "email": email, "org": org, "photo": photo}
        _redis.hset(f"visitor:record:{phone}", mapping=mapping)
        try:
            _update_name_index(name, phone)
        except Exception:
            pass
        return vid
    except Exception as exc:
        logger.exception("failed to save visitor {}: {}", phone, exc)
        raise RuntimeError("failed to save visitor") from exc


# save_host routine
def save_host(name: str, email: str = "", dept: str = "", location: str = "") -> None:
    if not _redis or not name:
        raise ValueError("Redis not initialized or name missing")
    try:
        mapping = {"email": email, "dept": dept, "location": location}
        _redis.hset(f"visitor:host:{name}", mapping=mapping)
    except Exception as exc:
        logger.exception("failed to save host {}: {}", name, exc)
        raise RuntimeError("failed to save host") from exc


# _decode_map routine
def _decode_map(data: Dict) -> Dict:
    return {
        k.decode() if isinstance(k, bytes) else k: (
            v.decode() if isinstance(v, bytes) else v
        )
        for k, v in data.items()
    }


def _fetch_visitor_record(phone: str) -> Dict[str, str]:
    """Fetch and decode a visitor record by phone."""
    if not _redis or not phone:
        return {}
    try:
        data = _redis.hgetall(f"visitor:record:{phone}")
    except Exception as exc:
        logger.exception("failed to fetch visitor {}: {}", phone, exc)
        return {}
    return _decode_map(data) if data else {}


# get_or_create_visitor routine
def get_or_create_visitor(
    name: str, phone: str, email: str = "", org: str = "", photo: str = ""
) -> str:
    """Return existing visitor_id by phone or create a new record."""
    if not _redis or not phone:
        return ""
    info = _fetch_visitor_record(phone)
    vid = info.get("id")
    if vid:
        if name or email or org or photo:
            mapping = {
                "name": name or info.get("name", ""),
                "email": email or info.get("email", ""),
                "org": org or info.get("org", ""),
                "photo": photo or info.get("photo", ""),
                "id": vid,
            }
            _redis.hset(f"visitor:record:{phone}", mapping=mapping)
        return vid
    vid = generate_id()
    mapping = {"id": vid, "name": name, "email": email, "org": org, "photo": photo}
    _redis.hset(f"visitor:record:{phone}", mapping=mapping)
    try:
        _update_name_index(name, phone)
    except Exception:
        pass
    return vid


# get_visitor_by_phone routine
def get_visitor_by_phone(phone: str) -> Optional[Dict[str, str]]:
    if not _redis or not phone:
        return None
    info = _fetch_visitor_record(phone)
    if not info:
        return None
    return {
        "id": info.get("id", ""),
        "name": info.get("name", ""),
        "email": info.get("email", ""),
        "org": info.get("org", ""),
        "photo": info.get("photo", ""),
    }


# get_host routine
def get_host(name: str) -> Optional[Dict[str, str]]:
    if not _redis or not name:
        return None
    try:
        data = _redis.hgetall(f"visitor:host:{name}")
    except Exception as exc:
        logger.exception("failed to fetch host {}: {}", name, exc)
        return None
    if not data:
        return None
    info = _decode_map(data)
    return {
        "email": info.get("email", ""),
        "dept": info.get("dept", ""),
        "location": info.get("location", ""),
    }


def _update_name_index(name: str, phone: str) -> None:
    if not _redis or not name:
        return
    member = f"{name.lower()}|{phone}"
    ts = time.time()
    _redis.zadd("visitor_name_idx", {member: ts})


def _iter_name_index(prefix_l: str, seen: set[tuple[str, str]]) -> Iterator[dict]:
    pattern = f"{prefix_l}*"
    for member, _score in _redis.zscan_iter(
        "visitor_name_idx", match=pattern, count=50
    ):
        mstr = member.decode() if isinstance(member, bytes) else member
        try:
            name, phone = mstr.split("|", 1)
        except ValueError:
            name, phone = mstr, ""
        key = (name, phone)
        if key in seen:
            continue
        seen.add(key)
        info = get_visitor_by_phone(phone) or {}
        yield {
            "name": info.get("name", name),
            "phone": phone,
            "visitor_type": info.get("visitor_type", ""),
            "company": info.get("org", ""),
            "photo_url": info.get("photo", ""),
        }


def _scan_logs(prefix_l: str, remaining: int, seen: set[tuple[str, str]]) -> list[dict]:
    try:
        entries = _redis.zrevrange("vms_logs", 0, -1)
    except Exception as exc:
        logger.exception("failed to scan visitor logs: {}", exc)
        return []
    results: list[dict] = []
    for e in entries:
        try:
            obj = json.loads(e if isinstance(e, str) else e.decode())
        except Exception:
            continue
        name = obj.get("name", "")
        if not name.lower().startswith(prefix_l):
            continue
        phone = obj.get("phone", "")
        key = (name, phone)
        if key in seen:
            continue
        seen.add(key)
        results.append(
            {
                "name": name,
                "phone": phone,
                "visitor_type": obj.get("visitor_type", ""),
                "company": obj.get("company_name", ""),
                "photo_url": obj.get("photo_url", ""),
            }
        )
        if len(results) >= remaining:
            break
    return results


# search_visitors_by_name routine
def search_visitors_by_name(prefix: str, limit: int = 5) -> list[dict]:
    """Return visitors whose names start with prefix."""
    if not _redis or not prefix:
        return []
    prefix_l = prefix.lower()
    seen: set[tuple[str, str]] = set()
    results = list(islice(_iter_name_index(prefix_l, seen), limit))
    if len(results) == limit:
        return results
    results.extend(_scan_logs(prefix_l, limit - len(results), seen))
    return results
