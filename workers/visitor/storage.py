from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from typing import Dict

import numpy as np


@dataclass
class VisitorRecord:
    """Data stored for each recognized visitor."""

    face_id: str
    ts: int
    cam_id: int
    image: str
    name: str = ""


class VisitorStorage:
    """Persistence layer for visitor data."""

    def __init__(self, redis):
        self.redis = redis

    def get_raw_face(self, face_id: str) -> Dict[str, str]:
        data = self.redis.hgetall(f"face:raw:{face_id}")
        return {
            (k.decode() if isinstance(k, bytes) else k): (
                v.decode() if isinstance(v, bytes) else v
            )
            for k, v in data.items()
        }

    def delete_raw_face(self, face_id: str) -> None:
        self.redis.delete(f"face:raw:{face_id}")

    def save_visitor(self, record: VisitorRecord) -> None:
        self.redis.hset(f"visitor:{record.face_id}", mapping=asdict(record))

    def load_known_embeddings(self) -> Dict[str, np.ndarray]:
        raw = self.redis.get("known_visitors")
        if not raw:
            return {}
        if isinstance(raw, bytes):
            raw = raw.decode()
        data = json.loads(raw)
        return {name: np.array(vec, dtype=np.float32) for name, vec in data.items()}
