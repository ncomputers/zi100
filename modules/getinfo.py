"""RTSP probe helper using FFmpeg.

This module wraps ``ffprobe`` and ``ffmpeg`` to fetch stream metadata and
estimate effective FPS. It tries both TCP and UDP transports with optional
hardware acceleration and picks the attempt with the most decoded frames.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import time
from collections import deque
from itertools import product
from typing import Any, Dict


def _require_ffmpeg() -> None:
    """Ensure ``ffmpeg`` and ``ffprobe`` are available."""
    for bin_name in ("ffmpeg", "ffprobe"):
        if shutil.which(bin_name) is None:
            raise RuntimeError(f"{bin_name} not found on PATH.")


def _run(cmd: list[str], timeout: int | None = None) -> tuple[int, str, str]:
    """Run a command returning ``(rc, stdout, stderr)``."""
    proc = subprocess.run(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=timeout,
        check=False,
        text=True,
    )
    return proc.returncode, proc.stdout or "", proc.stderr or ""


def _parse_rational(val: str | None) -> float | None:
    try:
        if not val or val == "0/0":
            return None
        num, den = val.split("/")
        num_f = float(num)
        den_f = float(den)
        if den_f == 0:
            return None
        return num_f / den_f
    except Exception:
        return None


def _ffprobe_video_stream_info(
    url: str, use_tcp: bool = True, probe_timeout: int = 12
) -> Dict[str, Any]:
    args = [
        "ffprobe",
        "-v",
        "error",
        "-show_streams",
        "-select_streams",
        "v:0",
        "-of",
        "json",
        "-analyzeduration",
        "1000000",
        "-probesize",
        "500000",
    ]
    if use_tcp:
        args += ["-rtsp_transport", "tcp"]
    rc, out, err = _run(args + [url], timeout=probe_timeout)
    if rc != 0:
        raise RuntimeError(f"ffprobe failed: {(out or err).strip()[:4000]}")
    data = json.loads(out)
    if not data.get("streams"):
        raise RuntimeError("No video stream found.")
    s = data["streams"][0]
    to_int = lambda x: int(x) if str(x).isdigit() else None
    return {
        "codec": s.get("codec_name"),
        "profile": s.get("profile"),
        "width": s.get("width"),
        "height": s.get("height"),
        "pix_fmt": s.get("pix_fmt"),
        "bit_rate_bps": to_int(s.get("bit_rate")),
        "avg_frame_rate_raw": s.get("avg_frame_rate"),
        "r_frame_rate_raw": s.get("r_frame_rate"),
        "avg_frame_rate": _parse_rational(s.get("avg_frame_rate")),
        "r_frame_rate": _parse_rational(s.get("r_frame_rate")),
        "time_base": s.get("time_base"),
        "start_time": s.get("start_time"),
        "nb_frames": to_int(s.get("nb_frames")),
    }


def _measure_with_ffmpeg(
    url: str, seconds: int = 8, transport: str = "tcp", hwaccel: bool = False
) -> Dict[str, Any]:
    """Decode the stream for ``seconds`` and parse ``-stats`` output."""
    cmd = [
        "ffmpeg",
        "-hide_banner",
        "-stats",
        "-loglevel",
        "info",
        "-analyzeduration",
        "1000000",
        "-probesize",
        "500000",
        "-rtsp_transport",
        "tcp" if transport == "tcp" else "udp",
    ]
    if hwaccel:
        cmd += ["-hwaccel", "auto"]
    cmd += [
        "-i",
        url,
        "-an",
        "-t",
        str(seconds),
        "-pix_fmt",
        "yuv420p",
        "-f",
        "null",
        "-",
    ]
    start = time.time()
    rc, out, err = _run(cmd, timeout=seconds + 40)
    elapsed = max(1e-6, time.time() - start)
    text = (err or "") + (out or "")
    frame_re = re.compile(r"frame=\s*(\d+)")
    frames = 0
    for m in frame_re.finditer(text):
        try:
            frames = int(m.group(1))
        except Exception:
            pass
    eff_fps = round(frames / elapsed, 3)
    tail = "\n".join(deque(text.strip().splitlines(), maxlen=60))
    return {
        "frames": frames,
        "elapsed_sec": round(elapsed, 3),
        "effective_fps": eff_fps,
        "transport": transport.upper(),
        "hwaccel": hwaccel,
        "rc": rc,
        "tail": tail,
    }


def _choose_best(results: list[Dict[str, Any]]) -> Dict[str, Any]:
    best = None
    for r in results:
        if best is None:
            best = r
            continue
        if r["frames"] > best["frames"]:
            best = r
        elif (
            r["frames"] == best["frames"] and r["effective_fps"] > best["effective_fps"]
        ):
            best = r
    return best or {}


def probe_rtsp(
    url: str, sample_seconds: int = 8, enable_hwaccel: bool = True
) -> Dict[str, Any]:
    """Probe ``url`` and return metadata with effective FPS estimates."""
    _require_ffmpeg()
    meta = _ffprobe_video_stream_info(url, use_tcp=True)
    attempts: list[Dict[str, Any]] = []
    combos = list(product(("tcp", "udp"), (True, False)))
    for transport, hwaccel in combos:
        if hwaccel and not enable_hwaccel:
            continue
        attempts.append(
            _measure_with_ffmpeg(
                url, sample_seconds, transport=transport, hwaccel=hwaccel
            )
        )
    best = _choose_best(attempts)
    return {
        "metadata": meta,
        "effective_fps": best.get("effective_fps"),
        "transport": best.get("transport"),
        "hwaccel": best.get("hwaccel"),
        "frames": best.get("frames"),
        "elapsed_sec": best.get("elapsed_sec"),
    }
