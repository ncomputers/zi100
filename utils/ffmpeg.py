from __future__ import annotations

import subprocess
from functools import lru_cache


@lru_cache(maxsize=2)
def _ffmpeg_has_option(opt: str) -> bool:
    """Return True if ``ffmpeg`` help lists ``opt``."""
    try:
        res = subprocess.run(
            ["ffmpeg", "-h"], capture_output=True, text=True, check=False
        )
    except Exception:
        return False
    return f"-{opt}" in res.stdout


def _build_timeout_flags(seconds: float) -> list[str]:
    """Return ``-stimeout`` and ``-rw_timeout`` flags if supported."""
    if not seconds:
        return []
    usec = str(int(seconds * 1_000_000))
    flags: list[str] = []
    if _ffmpeg_has_option("stimeout"):
        flags += ["-stimeout", usec]
    if _ffmpeg_has_option("rw_timeout"):
        flags += ["-rw_timeout", usec]
    return flags


def build_preview_cmd(
    url: str, transport: str, timeout: float, downscale: int | None = None
) -> list[str]:
    """Return ffmpeg command for generating an MJPEG preview."""
    cmd = [
        "ffmpeg",
        "-nostdin",
        "-hide_banner",
        "-loglevel",
        "error",
        "-nostats",
        "-rtsp_transport",
        transport,
    ]
    if timeout:
        cmd += _build_timeout_flags(timeout)
    cmd += ["-i", url]
    if downscale and downscale > 1:
        vf = f"scale=trunc(iw/{downscale}/2)*2:trunc(ih/{downscale}/2)*2"
        cmd += ["-vf", vf]
    cmd += [
        "-threads",
        "1",
        "-f",
        "mpjpeg",
        "-q:v",
        "5",
        "pipe:1",
    ]
    return cmd


def build_snapshot_cmd(
    url: str, transport: str, timeout: float, downscale: int | None = None
) -> list[str]:
    """Return ffmpeg command for capturing a single JPEG frame."""
    cmd = [
        "ffmpeg",
        "-nostdin",
        "-hide_banner",
        "-loglevel",
        "error",
        "-nostats",
        "-rtsp_transport",
        transport,
    ]
    if timeout:
        cmd += _build_timeout_flags(timeout)
    cmd += ["-i", url]
    if downscale and downscale > 1:
        vf = f"scale=trunc(iw/{downscale}/2)*2:trunc(ih/{downscale}/2)*2"
        cmd += ["-vf", vf]
    cmd += [
        "-threads",
        "1",
        "-frames:v",
        "1",
        "-f",
        "image2",
        "-q:v",
        "5",
        "pipe:1",
    ]
    return cmd
