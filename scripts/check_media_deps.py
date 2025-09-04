#!/usr/bin/env python3
"""Check presence of media processing dependencies."""
import sys
from shutil import which

import logging_config  # noqa: F401


def main() -> int:
    ffmpeg = which("ffmpeg") is not None
    gst = which("gst-launch-1.0") is not None
    if ffmpeg and gst:
        print("ffmpeg and gst-launch-1.0 available")
        return 0
    if not ffmpeg and not gst:
        print("Error: neither ffmpeg nor gst-launch-1.0 found", file=sys.stderr)
        return 1
    if not ffmpeg:
        print("Warning: ffmpeg not found; FFmpeg backend will be disabled")
    if not gst:
        print("Warning: gst-launch-1.0 not found; GStreamer backend will be disabled")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
