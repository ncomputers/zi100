"""Pre-start dependency checks for binaries and model files."""

from __future__ import annotations

from pathlib import Path
from shutil import which
from typing import List

from loguru import logger

from utils.gpu import assert_memory

try:  # optional heavy dependency
    import torch  # type: ignore
except ModuleNotFoundError:  # pragma: no cover - optional in tests
    torch = None

logger = logger.bind(module="preflight")


class DependencyError(RuntimeError):
    """Raised when a required dependency is missing."""


def check_dependencies(cfg: dict, base_dir: str | Path | None = None) -> None:
    """Validate presence of required binaries and model files.

    Args:
        cfg: Application configuration containing model file names.
        base_dir: Base directory to resolve relative model paths. Defaults to the
            repository root (one level above this file).

    Raises:
        DependencyError: If any binary or model file is missing.
    """
    base = Path(base_dir) if base_dir else Path(__file__).resolve().parents[1]

    ffmpeg_available = which("ffmpeg") is not None
    gst_available = which("gst-launch-1.0") is not None
    cfg["ffmpeg_available"] = ffmpeg_available
    cfg["gst_available"] = gst_available

    if not ffmpeg_available and not gst_available:
        raise DependencyError("Missing dependencies: ffmpeg, gst-launch-1.0")
    if not ffmpeg_available:
        logger.warning("'ffmpeg' not found; FFmpeg backend disabled")
    if not gst_available:
        logger.warning("'gst-launch-1.0' not found; GStreamer backend disabled")

    cuda_available = bool(torch and torch.cuda.is_available())
    cfg["cuda_available"] = cuda_available
    if cfg.get("require_cuda") and not cuda_available:
        raise DependencyError("CUDA device not available")

    min_mem = cfg.get("min_gpu_memory_gb")
    if cuda_available and min_mem:
        try:
            assert_memory(float(min_mem))
        except RuntimeError as exc:
            raise DependencyError(str(exc)) from exc

    missing: List[str] = []

    model_keys = ("person_model", "ppe_model", "plate_model")
    for key in model_keys:
        model = cfg.get(key)
        if not model:
            continue
        path = Path(model)
        if not path.is_file():
            path = base / model
        if not path.is_file():
            missing.append(model)

    if missing:
        raise DependencyError("Missing dependencies: " + ", ".join(missing))
