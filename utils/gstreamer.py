from __future__ import annotations

import shutil
import subprocess

from loguru import logger


def probe_gstreamer(cfg: dict) -> None:
    """Ensure GStreamer is available or disable related features."""
    if not cfg.get("enable_gstreamer", False):
        return
    gst_bin = shutil.which("gst-launch-1.0")
    if not gst_bin:
        logger.warning("gst-launch-1.0 not found; disabling GStreamer")
        cfg["enable_gstreamer"] = False
        return
    try:
        subprocess.run(
            [gst_bin, "--version"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True,
        )
    except (subprocess.CalledProcessError, OSError) as e:
        logger.warning(f"GStreamer check failed: {e}; disabling GStreamer")
        cfg["enable_gstreamer"] = False
