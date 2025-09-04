"""Redis helper for storing user feedback."""

from __future__ import annotations

from typing import Dict, List

import redis
from loguru import logger

from utils.ids import generate_id

_IDS_KEY = "feedback:ids"


def _decode_map(data: Dict) -> Dict:
    return {
        k.decode() if isinstance(k, bytes) else k: (
            v.decode() if isinstance(v, bytes) else v
        )
        for k, v in data.items()
    }


def create_feedback(redis_client: redis.Redis, data: Dict[str, str]) -> str:
    """Persist a feedback record and return its generated ID."""
    fid = generate_id()
    mapping = {"id": fid, **data}
    try:
        redis_client.hset(f"feedback:entry:{fid}", mapping=mapping)
        redis_client.sadd(_IDS_KEY, fid)
    except Exception as exc:
        logger.exception("failed to store feedback {}", exc)
        raise RuntimeError("failed to store feedback") from exc
    return fid


def list_feedback(redis_client: redis.Redis) -> List[Dict[str, str]]:
    """Return all stored feedback records."""
    ids = redis_client.smembers(_IDS_KEY)
    results: List[Dict[str, str]] = []
    for raw_id in ids:
        fid = raw_id.decode() if isinstance(raw_id, bytes) else raw_id
        data = redis_client.hgetall(f"feedback:entry:{fid}")
        if data:
            results.append(_decode_map(data))
    return results


def update_status(redis_client: redis.Redis, feedback_id: str, status: str) -> None:
    """Update status for a feedback record."""
    redis_client.hset(f"feedback:entry:{feedback_id}", "status", status)
