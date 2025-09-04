from __future__ import annotations

import os

import cv2
import psutil
from loguru import logger

try:  # optional dependency
    import torch  # type: ignore
except ModuleNotFoundError:  # pragma: no cover - used only when torch missing
    torch = None


def _calc_w(workers: int | None, pct: int, cores: int) -> int:
    """Return worker count based on explicit workers or CPU percentage."""
    if workers is not None:
        return max(1, workers)
    if not 1 <= pct <= 100:
        raise ValueError("cpu_limit_percent must be between 1 and 100")
    return max(1, int(cores * pct / 100))


def apply_thread_limits(cfg: dict, workers: int | None = None) -> int:
    """Apply CPU affinity and library thread limits."""
    cores = os.cpu_count() or 1
    w = _calc_w(workers, int(cfg.get("cpu_limit_percent", 50)), cores)
    psutil.Process().cpu_affinity(list(range(w)))
    if hasattr(cv2, "setNumThreads"):
        cv2.setNumThreads(w)
    if torch is not None:
        torch.set_num_threads(w)
    logger.info(f"Threads={w}, cores={cores}")
    return w


__all__ = ["_calc_w", "apply_thread_limits"]
