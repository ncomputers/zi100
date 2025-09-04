"""Helper functions for the face engine."""

from __future__ import annotations

from typing import List

import cv2
import numpy as np
from config import FACE_THRESHOLDS
from utils.image import decode_base64_image


# load_image routine
def load_image(data: bytes | str) -> np.ndarray | None:
    """Load an image from raw bytes or base64 string."""
    if isinstance(data, str):
        try:
            data = decode_base64_image(data)
        except ValueError:
            return None
    arr = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
    return arr


# crop_face routine
def crop_face(image: np.ndarray, bbox: List[int]) -> np.ndarray:
    x1, y1, x2, y2 = bbox
    x1, y1 = max(x1, 0), max(y1, 0)
    return image[y1:y2, x1:x2].copy()


# resize routine
def resize(image: np.ndarray, max_size: int = 800) -> np.ndarray:
    h, w = image.shape[:2]
    scale = max_size / max(h, w)
    if scale < 1:
        image = cv2.resize(image, (int(w * scale), int(h * scale)))
    return image


# is_blurry routine
def is_blurry(
    image: np.ndarray, threshold: float = FACE_THRESHOLDS.blur_detection
) -> bool:
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    fm = cv2.Laplacian(gray, cv2.CV_64F).var()
    return fm < threshold


# face_count routine
def face_count(image: np.ndarray, detector) -> int:
    rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
    return len(detector.detect(rgb))
