#!/usr/bin/env python3
"""RTSP → MJPEG browser preview (no audio).

This script exposes a simple Flask app that converts an RTSP stream to an
MJPEG browser preview using FFmpeg. The logic is based on a tested approach
and intentionally kept minimal.
"""

import os
import signal
import subprocess
import threading
import time

from flask import Flask, Response

# The camera URL. Set the RTSP_URL environment variable to override.
RTSP_URL = os.environ.get(
    "RTSP_URL",
    "rtsp://user:pass@192.168.31.11:554/cam/realmonitor?channel=1&subtype=1",
)

HOST, PORT = "0.0.0.0", 8002
FFMPEG = "ffmpeg"

# Prefer TCP unless you *know* your cam wants UDP.
RTSP_TRANSPORT = os.environ.get("RTSP_TRANSPORT", "tcp")  # "tcp" or "udp"

# Output tuning
FPS = "12"  # 8–15 typical
QUALITY = "5"  # 2 = better JPEG (bigger), 7 = worse (smaller)

app = Flask(__name__)
_proc = None
_lock = threading.Lock()


def ffmpeg_cmd():
    """Construct the FFmpeg command for streaming."""
    # NOTE:
    # - removed "-flags low_delay" (breaks MJPEG)
    # - keep it minimal (no -reconnect*, no -stimeout)
    # - mpjpeg muxer emits proper multipart boundaries named "frame"
    return [
        FFMPEG,
        "-rtsp_transport",
        RTSP_TRANSPORT,
        "-i",
        RTSP_URL,
        "-an",  # no audio
        "-r",
        FPS,  # output fps
        "-vf",
        "scale=trunc(iw/2)*2:trunc(ih/2)*2",  # even dims
        "-pix_fmt",
        "yuvj420p",  # MJPEG-friendly
        "-fflags",
        "nobuffer+genpts",
        "-threads",
        "1",  # MJPEG encoder is happier single-threaded
        "-f",
        "mpjpeg",
        "-q:v",
        QUALITY,
        "-boundary_tag",
        "frame",
        "pipe:1",
    ]


def start_ffmpeg():
    """Start the FFmpeg subprocess."""
    global _proc
    stop_ffmpeg()
    cmd = ffmpeg_cmd()
    print("Starting FFmpeg:", " ".join(cmd))
    _proc = subprocess.Popen(
        cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, bufsize=0
    )


def stop_ffmpeg():
    """Stop the FFmpeg subprocess if running."""
    global _proc
    if _proc and _proc.poll() is None:
        try:
            _proc.send_signal(signal.SIGINT)
            _proc.wait(timeout=2)
        except Exception:
            _proc.kill()
    _proc = None


def stderr_logger():
    """Continuously log stderr output from FFmpeg."""
    while True:
        with _lock:
            p = _proc
        if not p:
            time.sleep(0.2)
            continue
        line = p.stderr.readline()
        if not line:
            if p.poll() is not None:
                time.sleep(0.2)
            continue
        print("[ffmpeg]", line.decode(errors="ignore").rstrip())


def mjpeg_bytes():
    """Yield MJPEG bytes from FFmpeg."""
    while True:
        with _lock:
            if _proc is None or _proc.poll() is not None:
                start_ffmpeg()
            p = _proc
        try:
            chunk = p.stdout.read(32768)
            if not chunk:
                stop_ffmpeg()
                time.sleep(0.2)
                continue
            yield chunk  # already valid multipart MJPEG
        except GeneratorExit:
            break
        except Exception:
            time.sleep(0.1)


@app.route("/")
def index():
    """Serve a simple HTML page with the MJPEG stream."""
    ts = int(time.time() * 1000)  # cache-bust
    html = f"""<!doctype html>
<html><head>
<meta charset="utf-8"/><title>RTSP Preview</title>
<meta name="viewport" content="width=device-width,initial-scale=1"/>
<style>
  html,body{{height:100%;margin:0;background:#0b0f14;color:#e6eef7;font-family:system-ui,Segoe UI,Roboto,Arial}}
  .wrap{{display:flex;align-items:center;justify-content:center;height:100%}}
  .card{{width:min(100%,1000px);background:#111826;border-radius:16px;box-shadow:0 10px 30px rgba(0,0,0,.35);padding:20px}}
  img{{width:100%;height:auto;background:#000;border-radius:12px}}
  .tip{{margin-top:8px;opacity:.75;font-size:13px}}
</style>
</head><body>
  <div class="wrap"><div class="card">
    <h3>Live Stream (MJPEG)</h3>
    <img src="/mjpeg?ts={ts}" alt="stream"/>
    <div class="tip">No audio. If it doesn’t appear, refresh. Watch the terminal for [ffmpeg] logs.</div>
  </div></div>
</body></html>"""
    return Response(html, mimetype="text/html")


@app.route("/mjpeg")
def mjpeg():
    """Return multipart MJPEG stream."""
    return Response(mjpeg_bytes(), mimetype="multipart/x-mixed-replace; boundary=frame")


if __name__ == "__main__":
    start_ffmpeg()
    threading.Thread(target=stderr_logger, daemon=True).start()
    print(f"Open http://{HOST}:{PORT}")
    try:
        app.run(host=HOST, port=PORT, threaded=True)
    finally:
        stop_ffmpeg()
