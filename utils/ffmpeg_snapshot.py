from __future__ import annotations

import subprocess

from loguru import logger


def capture_snapshot(url: str) -> bytes:
    """Return a single JPEG frame from ``url`` using ffmpeg.

    Raises ``RuntimeError`` if the command fails.
    """
    cmd = [
        "ffmpeg",
        "-nostdin",
        "-hide_banner",
        "-loglevel",
        "error",
        "-rtsp_transport",
        "tcp",
        "-i",
        url,
        "-frames:v",
        "1",
        "-f",
        "image2",
        "pipe:1",
    ]
    logger.debug("snapshot cmd: {}", " ".join(cmd))
    res = subprocess.run(
        cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False
    )
    if res.returncode != 0:
        raise RuntimeError(res.stderr.decode(errors="replace").strip())
    return res.stdout
