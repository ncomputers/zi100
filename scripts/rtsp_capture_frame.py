#!/usr/bin/env python3
"""Capture a single frame from an RTSP stream using FFmpeg."""

import argparse
import logging
import time
from pathlib import Path

import ffmpeg


def probe_resolution(url: str) -> tuple[int | None, int | None]:
    """Return the first video stream's (width, height) if available."""
    try:
        info = ffmpeg.probe(url)
    except ffmpeg.Error as exc:  # pragma: no cover - logging path
        logging.error("ffprobe error: %s", exc)
        return None, None

    for stream in info.get("streams", []):
        if stream.get("codec_type") == "video":
            return int(stream["width"]), int(stream["height"])
    return None, None


def capture_frame(url: str, path: Path) -> bool:
    """Save a single frame from *url* to *path*."""
    try:
        (
            ffmpeg.input(url, rtsp_transport="tcp")
            .output(str(path), vframes=1)
            .overwrite_output()
            .run(quiet=True)
        )
        return True
    except ffmpeg.Error as exc:  # pragma: no cover - logging path
        logging.error("ffmpeg error: %s", exc)
        return False


def main() -> int:
    parser = argparse.ArgumentParser(description="Capture a frame from an RTSP stream")
    parser.add_argument("url", help="RTSP URL")
    parser.add_argument(
        "-o", "--output", help="Output image path", default=None, metavar="PATH"
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    width, height = probe_resolution(args.url)
    if width and height:
        logging.info("Stream resolution: %dx%d", width, height)
    else:
        logging.warning("Unable to determine stream resolution")

    out_path = (
        Path(args.output) if args.output else Path(f"frame_{int(time.time())}.jpg")
    )
    if capture_frame(args.url, out_path):
        logging.info("Frame saved to %s", out_path.resolve())
        return 0

    logging.error("Failed to capture frame")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
