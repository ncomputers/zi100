"""Face detector wrapper using InsightFace when available."""

from __future__ import annotations

from typing import List

import cv2
import numpy as np
import psutil
from loguru import logger

try:  # optional heavy dependency
    import torch  # type: ignore
except ModuleNotFoundError:  # pragma: no cover - torch optional in tests
    torch = None

FaceAnalysis = None  # InsightFace dependency removed

from utils.gpu import get_device


class FaceDetector:
    """Thin wrapper around an InsightFace detector."""

    def __init__(self, model: str = "buffalo_l") -> None:
        self.model = model
        self.app = None
        if FaceAnalysis is not None:
            mem = psutil.virtual_memory()
            logger.debug(
                f"Before loading face detector model: RAM available {mem.available / (1024**3):.2f} GB"
            )
            device = get_device()
            if getattr(device, "type", "") == "cuda" and torch:
                free, _ = torch.cuda.mem_get_info(device)
                logger.debug(
                    f"Before loading face detector model: GPU available {free / (1024**3):.2f} GB"
                )
            try:
                self.app = FaceAnalysis(name=model)
                self.app.prepare(ctx_id=0, det_size=(640, 640))
            except RuntimeError as e:
                raise RuntimeError(
                    f"Failed to load InsightFace model: {e}. Disable face detection or use smaller weights."
                ) from e
            except Exception:
                self.app = None

    # detect routine
    def detect(self, image: np.ndarray) -> List[object]:
        """Return face objects detected in ``image``.

        Parameters
        ----------
        image: np.ndarray
            RGB image array.
        """
        if self.app is None:
            return []
        return self.app.get(image)

    # detect_boxes routine
    def detect_boxes(self, image: np.ndarray) -> List[List[int]]:
        """Return bounding boxes for faces in ``image``."""
        faces = self.detect(image)
        return [list(map(int, f.bbox)) for f in faces]
