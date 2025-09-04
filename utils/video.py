"""Video utilities."""

from __future__ import annotations

import asyncio
import json
import logging
import subprocess

logger = logging.getLogger(__name__)


def get_stream_resolution(url: str) -> tuple[int, int]:
    """Return ``(width, height)`` for the first video stream in ``url``.

    Falls back to ``(640, 480)`` if probing fails and logs a warning.
    """
    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-select_streams",
        "v:0",
        "-show_entries",
        "stream=width,height",
        "-of",
        "json",
        url,
    ]
    fallback = (640, 480)
    logger.debug("ffprobe command: %s", " ".join(cmd))
    try:
        proc = subprocess.run(
            cmd, capture_output=True, text=True, check=True, timeout=5
        )
        info = json.loads(proc.stdout or "{}")
        streams = info.get("streams", [])
        if streams:
            stream = streams[0]
            width = int(stream.get("width", fallback[0]))
            height = int(stream.get("height", fallback[1]))
            return width, height
        logger.debug("ffprobe stdout: %s", proc.stdout)
        logger.debug("ffprobe stderr: %s", proc.stderr)
        logger.warning(
            "ffprobe returned no streams for %s; falling back to %dx%d", url, *fallback
        )
    except (
        subprocess.CalledProcessError,
        json.JSONDecodeError,
        subprocess.TimeoutExpired,
    ) as exc:
        logger.debug("ffprobe stdout: %s", getattr(exc, "stdout", ""))
        logger.debug("ffprobe stderr: %s", getattr(exc, "stderr", ""))
        logger.warning(
            "ffprobe failed for %s (%s: %s); falling back to %dx%d",
            url,
            type(exc).__name__,
            exc,
            *fallback,
        )
    except (OSError, ValueError) as exc:
        logger.warning(
            "ffprobe error for %s (%s: %s); falling back to %dx%d",
            url,
            type(exc).__name__,
            exc,
            *fallback,
        )
    return fallback


async def async_get_stream_resolution(url: str) -> tuple[int, int]:
    """Async wrapper around :func:`get_stream_resolution`.

    Executes the blocking probe in a thread and returns ``(640, 480)`` on
    failure or timeout.
    """
    fallback = (640, 480)
    try:
        return await asyncio.to_thread(get_stream_resolution, url)
    except (OSError, RuntimeError, ValueError) as exc:
        logger.warning(
            "async probe failed for %s (%s: %s); falling back to %dx%d",
            url,
            type(exc).__name__,
            exc,
            *fallback,
        )
        return fallback
