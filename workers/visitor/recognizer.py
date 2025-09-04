from __future__ import annotations

import json
from collections import deque
from typing import Dict, Optional

import cv2
import numpy as np
from config import FACE_THRESHOLDS


def _blur_score(img: np.ndarray) -> float:
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    return float(cv2.Laplacian(gray, cv2.CV_64F).var())


class FaceRecognizer:
    """Basic face recognition helper."""

    def __init__(self, cfg: dict, redis):
        self.cfg = cfg
        self.redis = redis
        self.last_embeddings = deque(maxlen=10)
        self.known = self._load_known()
        self.app = None  # injected external model

    def _load_known(self) -> Dict[str, np.ndarray]:
        raw = self.redis.get("known_visitors")
        if not raw:
            return {}
        if isinstance(raw, bytes):
            raw = raw.decode()
        data = json.loads(raw)
        return {name: np.array(vec, dtype=np.float32) for name, vec in data.items()}

    def identify(self, emb: np.ndarray) -> Optional[str]:
        if not self.known:
            return None
        thresh = self.cfg.get(
            "face_match_thresh", FACE_THRESHOLDS.recognition_match
        )
        names = list(self.known.keys())
        arr = np.stack([self.known[n] for n in names])
        dists = np.linalg.norm(arr - emb, axis=1)
        idx = int(np.argmin(dists))
        if dists[idx] < thresh:
            return names[idx]
        return None

    def is_duplicate(self, emb: np.ndarray) -> bool:
        thresh = self.cfg.get(
            "face_duplicate_thresh", FACE_THRESHOLDS.duplicate_suppression
        )
        for prev in self.last_embeddings:
            if float(np.linalg.norm(prev - emb)) < thresh:
                return True
        self.last_embeddings.append(emb)
        return False

    def detect(self, img):
        if self.app is None:
            return []
        return self.app.get(img)
