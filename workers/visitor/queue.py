from __future__ import annotations

from typing import Optional


class VisitorQueue:
    """Simple Redis-backed FIFO queue for visitor face IDs."""

    def __init__(self, redis, name: str = "visitor_queue"):
        self.redis = redis
        self.name = name

    def push(self, face_id: str) -> None:
        """Push a face identifier onto the queue."""
        self.redis.rpush(self.name, face_id)

    def pop(self) -> Optional[str]:
        """Pop the next face identifier from the queue."""
        item = self.redis.lpop(self.name)
        if item is None:
            return None
        if isinstance(item, bytes):
            return item.decode()
        return item
