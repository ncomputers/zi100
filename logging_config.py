"""Central Loguru configuration for structured logging."""

from __future__ import annotations

import os
import shutil
import sys
import threading
from pathlib import Path

from loguru import logger

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
LOG_PATH = Path(os.getenv("LOG_PATH", "logs/app.log"))
LOG_ROTATION = os.getenv("LOG_ROTATION", "10 MB")
LOG_RETENTION = os.getenv("LOG_RETENTION", "7 days")
# Bytes required to enable file logging (default 50 MB)
MIN_FREE_SPACE = 50 * 1024 * 1024
# Set to a truthy value to disable file logging entirely
DISABLE_FILE_LOGGING = os.getenv("DISABLE_FILE_LOGGING", "").lower() in {
    "1",
    "true",
    "yes",
}

LOG_PATH.parent.mkdir(parents=True, exist_ok=True)

_lock = threading.Lock()
_sink_ids: list[int] = []


def _configure(level: str = LOG_LEVEL) -> None:
    """Configure Loguru sinks with structured JSON output in a thread-safe manner."""
    global _sink_ids
    with _lock:
        for sink_id in _sink_ids:
            logger.remove(sink_id)
        _sink_ids = [
            logger.add(
                sys.stdout,
                level=level,
                enqueue=True,
                serialize=True,
            )
        ]

    if DISABLE_FILE_LOGGING:
        logger.warning(
            "File logging disabled via DISABLE_FILE_LOGGING environment variable"
        )
        return

    free_space = shutil.disk_usage(LOG_PATH.parent).free
    if free_space < MIN_FREE_SPACE:
        logger.warning(
            "Insufficient disk space for %s; skipping file logging (%.2f MB free)",
            LOG_PATH,
            free_space / (1024 * 1024),
        )
        return

    with _lock:
        _sink_ids.append(
            logger.add(
                LOG_PATH,
                rotation=LOG_ROTATION,
                retention=LOG_RETENTION,
                level=level,
                enqueue=True,
                serialize=True,
            )
        )


def set_log_level(level: str) -> None:
    """Update logger level at runtime."""
    _configure(level)


_configure()
