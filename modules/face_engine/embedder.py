"""Face embedding utilities."""

from __future__ import annotations

from typing import List

import cv2
import numpy as np

from .detector import FaceDetector


class FaceEmbedder:
    """Compute embeddings for faces using ``FaceDetector``."""

    def __init__(self, detector: FaceDetector) -> None:
        self.detector = detector

    # get_embeddings routine
    def get_embeddings(self, image: np.ndarray) -> List[np.ndarray]:
        """Return normalized embeddings for all faces in ``image``."""
        faces = self.detector.detect(image)
        embs: List[np.ndarray] = []
        for face in faces:
            emb = face.embedding.astype(np.float32)
            norm = np.linalg.norm(emb)
            if norm > 0:
                emb /= norm
            embs.append(emb)
        return embs

    # embed_bytes routine
    def embed_bytes(self, data: bytes) -> List[np.ndarray]:
        """Decode ``data`` and return embeddings."""
        arr = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
        if arr is None:
            return []
        rgb = cv2.cvtColor(arr, cv2.COLOR_BGR2RGB)
        return self.get_embeddings(rgb)
