#!/usr/bin/env python3
"""Check RTSP stream availability across backends.

This script attempts to open the provided RTSP URL using FFmpeg,
GStreamer and OpenCV backends, printing whether each succeeded or
showing the captured stderr output on failure.
"""

from __future__ import annotations

import argparse
import contextlib
import io
import subprocess

import logging_config  # noqa: F401


def _run(name: str, cmd: list[str]) -> bool:
    """Run *cmd* and report success or stderr."""
    proc = subprocess.run(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    if proc.returncode == 0:
        print(f"{name}: success")
        return True
    print(f"{name}: failure")
    if proc.stderr:
        print(proc.stderr.strip())
    return False


def _opencv(url: str) -> bool:
    """Attempt to open *url* with OpenCV."""
    import cv2

    buf = io.StringIO()
    with contextlib.redirect_stderr(buf):
        cap = cv2.VideoCapture(url)
        ret, _ = cap.read()
        cap.release()
    err = buf.getvalue().strip()
    if ret:
        print("OpenCV: success")
        return True
    print("OpenCV: failure")
    if err:
        print(err)
    return False


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate RTSP backends")
    parser.add_argument("url", help="RTSP URL to test")
    url = parser.parse_args().url

    ok = []
    ok.append(
        _run(
            "FFmpeg",
            [
                "ffmpeg",
                "-rtsp_transport",
                "tcp",
                "-i",
                url,
                "-t",
                "1",
                "-f",
                "null",
                "-",
            ],
        )
    )
    ok.append(
        _run(
            "GStreamer",
            [
                "gst-launch-1.0",
                "-q",
                "rtspsrc",
                f"location={url}",
                "!",
                "fakesink",
            ],
        )
    )
    ok.append(_opencv(url))
    return 0 if all(ok) else 1


if __name__ == "__main__":
    raise SystemExit(main())
