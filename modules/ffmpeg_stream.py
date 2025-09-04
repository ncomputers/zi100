"""Camera stream using FFmpeg with a rolling buffer."""

from __future__ import annotations

import os
import shlex
import subprocess
import threading
import time
from collections import deque
from functools import lru_cache
from typing import Optional, Sequence, Tuple
from urllib.parse import urlparse

import ffmpeg
import numpy as np
from loguru import logger

from config import config as shared_config

from .base_camera import BaseCameraStream

logger = logger.bind(module="ffmpeg_stream")

PIXEL_FORMAT_BYTES = {
    "bgr24": 3,
    "rgb24": 3,
    "gray": 1,
    "gray8": 1,
    "bgra": 4,
    "rgba": 4,
}

ERROR_PATTERNS = {
    # authentication issues
    "401 Unauthorized": (
        "auth",
        "Authentication failed",
        "Verify username and password",
    ),
    "403 Forbidden": (
        "auth",
        "Authentication failed",
        "Verify username and password",
    ),
    "404 Not Found": (
        "not_found",
        "Stream not found",
        "Check camera URL/path",
    ),
    # rtsp/setup issues
    "method SETUP failed: 461": (
        "rtsp",
        "RTSP setup failed",
        "Camera may not support requested transport",
    ),
    # dns resolution failures
    "Temporary failure in name resolution": (
        "dns",
        "DNS lookup failed",
        "Check network DNS settings",
    ),
    "Name or service not known": (
        "dns",
        "DNS lookup failed",
        "Check network DNS settings",
    ),
    # connection issues
    "Connection timed out": (
        "timeout",
        "Connection timed out",
        "Verify camera is online and reachable",
    ),
    "No route to host": (
        "network",
        "No route to host",
        "Check network routing",
    ),
    "Connection refused": (
        "network",
        "Connection refused",
        "Ensure camera is running and port is correct",
    ),
    "Network is unreachable": (
        "network",
        "Network is unreachable",
        "Check local network connection",
    ),
    "Connection reset by peer": (
        "network",
        "Connection reset",
        "Check network stability",
    ),
    # codec/decoder issues
    "Unknown decoder": (
        "codec",
        "Unknown decoder",
        "Stream uses unsupported codec",
    ),
    "Invalid data": (
        "codec",
        "Invalid data",
        "Stream contains invalid or corrupted data",
    ),
    # ffmpeg missing
    "ffmpeg: not found": (
        "missing",
        "FFmpeg not installed",
        "Install FFmpeg",
    ),
}


@lru_cache(maxsize=1)
def _supports_drop() -> bool:
    """Return True if the running FFmpeg supports the ``-drop`` option."""
    try:
        result = subprocess.run(
            ["ffmpeg", "-h"], capture_output=True, text=True, check=False
        )
    except Exception:
        return False
    return "-drop" in result.stdout


# FFmpegCameraStream class encapsulates ffmpegcamerastream behavior
class FFmpegCameraStream(BaseCameraStream):
    """Capture frames using FFmpeg and keep only the latest N."""

    # __init__ routine
    def __init__(
        self,
        url: str,
        width: Optional[int] = None,
        height: Optional[int] = None,
        transport: str = "tcp",
        retry_transports: list[str] | None = None,
        buffer_size: int = 3,
        buffer_seconds: int | None = None,
        start_thread: bool = True,
        extra_flags: str | Sequence[str] | None = None,
        reconnect_delay: float = 1.0,
        command: str | list[str] | None = None,
        cam_id: int | str | None = None,
        frame_skip: int = 1,
        test: bool = False,
        downscale: int | None = None,
        mirror: bool = False,
        orientation: str = "vertical",
        timeout: float = 5.0,
    ) -> None:

        from utils.url import normalize_stream_url

        self.url = normalize_stream_url(url)
        parsed = urlparse(self.url)
        self._ip = parsed.hostname or "unknown"
        self._port = parsed.port or (554 if parsed.scheme == "rtsp" else 80)
        self.width = width
        self.height = height
        self._explicit_size = width is not None and height is not None
        # list of transports to try when no frames are received
        transport = transport.lower()
        self.retry_transports = [
            t.lower() for t in (retry_transports or ["tcp", "udp"])
        ]
        if transport in self.retry_transports:
            self.retry_transports.remove(transport)
        self.retry_transports.insert(0, transport)
        self._transport_index = 0
        self.transport = self.retry_transports[0]
        self.buffer_seconds = buffer_seconds
        self.pipeline: str = ""
        self.command = command
        self.test = test
        self.downscale = downscale
        self.mirror = mirror
        self.orientation = orientation
        self.extra_flags: list[str] = []
        if extra_flags and command is None:
            if isinstance(extra_flags, str):
                self.extra_flags = shlex.split(extra_flags)
            else:
                self.extra_flags = [str(f) for f in extra_flags]
        self.reconnect_delay = reconnect_delay
        self.timeout = timeout
        self.high_watermark = shared_config.get("ffmpeg_high_watermark", 0)
        self.low_watermark = shared_config.get("ffmpeg_low_watermark", 0)
        self.logger = logger.bind(cam_id=cam_id, backend="ffmpeg")
        self.frame_skip = max(1, frame_skip)
        self.network_error_count = 0
        self.network_error_threshold = int(
            shared_config.get("ffmpeg_network_error_threshold", 3)
        )

        self.ffmpeg_drop_enabled = _supports_drop()
        watermarks_configured = bool(self.high_watermark)
        drop_supported = self.ffmpeg_drop_enabled
        if shared_config.get("duplicate_filter_enabled", False) and not (
            self.ffmpeg_drop_enabled and watermarks_configured
        ):
            from .duplicate_filter import DuplicateFilter

            threshold = shared_config.get("duplicate_filter_threshold", 2)
            bypass = shared_config.get("duplicate_bypass_seconds", 2)
            self.dup_filter = DuplicateFilter(threshold, bypass)
            if self.high_watermark and not self.ffmpeg_drop_enabled:
                self.logger.warning(
                    "FFmpeg missing -drop support; enabling Python duplicate filter"
                )
        else:
            self.dup_filter = None
            if self.ffmpeg_drop_enabled and watermarks_configured:

                self.logger.info(
                    "FFmpeg dropping enabled; Python duplicate filter disabled",
                )
        self.pix_fmt = "bgr24"
        self.channels = PIXEL_FORMAT_BYTES.get(self.pix_fmt, 3)
        self._probe_stream()
        if self.test and self.downscale and self.downscale > 1:
            self.width //= self.downscale
            self.height //= self.downscale
        bytes_per_pixel = PIXEL_FORMAT_BYTES.get(self.pix_fmt, 3)
        self.channels = bytes_per_pixel
        self.frame_size = self.width * self.height * bytes_per_pixel
        self.logger.debug(
            "Initialized FFmpegCameraStream with frame_size={}",
            self.frame_size,
        )
        self.proc: Optional[subprocess.Popen] = None
        if command:
            if isinstance(command, list):
                self.cmd = command
                self.pipeline = " ".join(command)
            else:
                self.pipeline = command
                try:
                    self.cmd = shlex.split(command)
                except ValueError:
                    self.cmd = ["ffmpeg"]
            self.last_command = self.pipeline
        else:
            self.cmd = None
            self.pipeline = ""
            self.last_command = ""
        self.last_status: str = "ok"
        self.last_error: str = ""
        self._stderr_buffer = deque(maxlen=200)

        self._stderr_thread: threading.Thread | None = None
        self._stderr_stop = threading.Event()
        self.last_stderr: str = ""
        self.first_frame_timeout = float(shared_config.get("ready_timeout", 15.0))
        self._first_frame_start = time.time()
        self._successful_transport: str | None = None
        super().__init__(buffer_size, start_thread=start_thread)
        if not start_thread:
            self._init_stream()

    # _probe_stream routine
    def _probe_stream(self) -> None:
        """Probe stream dimensions and pixel format using ffprobe."""
        try:
            info = ffmpeg.probe(
                self.url,
                rtsp_transport=self.transport,
                select_streams="v:0",
                show_entries="stream=width,height,pix_fmt",
                v="error",
            )
            streams = info.get("streams", [])
            for stream in streams:
                if stream.get("codec_type") == "video":
                    w = int(stream.get("width", 640))
                    h = int(stream.get("height", 480))
                    src_fmt = stream.get("pix_fmt", "unknown")
                    self.logger.info(
                        "Probed stream resolution: {}x{} {}", w, h, src_fmt
                    )
                    if self.width is None:
                        self.width = w
                    if self.height is None:
                        self.height = h
                    return
        except Exception as e:
            self.logger.warning(
                "ffprobe failed: {}. Falling back to default 640x480 dimensions", e
            )
        self.logger.info("Probed stream resolution: {}x{} {}", 640, 480, self.pix_fmt)
        if self.width is None:
            self.width = 640
        if self.height is None:
            self.height = 480

    def build_ffmpeg_cmd(self) -> list[str]:
        """Return the full FFmpeg command."""
        cmd = ["ffmpeg", "-nostdin", "-threads", "1"]

        if self.high_watermark:
            if self.ffmpeg_drop_enabled:
                cmd += ["-drop", "true", "-h", str(self.high_watermark)]
                if self.low_watermark:
                    cmd += ["-l", str(self.low_watermark)]
            else:
                self.logger.debug(
                    "FFmpeg missing -drop support; skipping watermark flags",
                )

        if self.url.startswith("rtsp://"):
            cmd += ["-rtsp_transport", self.transport]
            if self.transport == "tcp":
                cmd += ["-rtsp_flags", "prefer_tcp"]

        timeout = str(int(self.timeout * 1_000_000))
        cmd += [
            "-rw_timeout",
            timeout,
            "-stimeout",
            timeout,
            "-reconnect",
            "1",
            "-reconnect_streamed",
            "1",
            "-reconnect_delay_max",
            str(self.reconnect_delay),
        ]

        cmd += [
            "-fflags",
            "nobuffer+discardcorrupt",
            "-flags",
            "low_delay",
            "-fflags",
            "+genpts",
            "-analyzeduration",
            "1000000",
            "-probesize",
            "500000",
        ]

        if self.extra_flags:
            cmd += self.extra_flags

        cmd += ["-i", self.url]

        filters: list[str] = []
        if self.test:
            filters.append("fps=1")
            if self.downscale and self.downscale > 1:
                filters.append(f"scale=iw/{self.downscale}:ih/{self.downscale}")
        else:
            if self.downscale and self.downscale > 1:
                filters.append(f"scale=iw/{self.downscale}:ih/{self.downscale}")

        if self._explicit_size and self.width and self.height:
            filters.append(f"scale={self.width}:{self.height}")

        if self.mirror:
            filters.append("hflip")

        if self.orientation == "rotate_90":
            filters.append("transpose=1")
        elif self.orientation == "rotate_180":
            filters.append("transpose=2,transpose=2")
        elif self.orientation == "rotate_270":
            filters.append("transpose=2")

        if filters:
            cmd += ["-vf", ",".join(filters)]
        if self.test:
            cmd += ["-t", "2"]

        cmd += [
            "-vcodec",
            "rawvideo",
            "-pix_fmt",
            "bgr24",
            "-f",
            "rawvideo",
            "-",
        ]

        return cmd

    # _start_process routine
    def _start_process(self) -> None:
        if self.cmd is None:
            cmd = self.build_ffmpeg_cmd()
            self.pipeline = " ".join(cmd)
            self.cmd = cmd
            self.last_command = self.pipeline
            self.logger.info("FFmpeg pipeline: {}", self.pipeline)
            if self.extra_flags:
                self.logger.info("FFmpeg custom flags: {}", " ".join(self.extra_flags))
        else:
            cmd = self.cmd
            if "-nostdin" not in cmd:
                cmd.insert(1, "-nostdin")
            self.logger.info("FFmpeg custom command: {}", self.pipeline)
        self._stderr_buffer.clear()
        self._stderr_stop.clear()
        self.last_stderr = ""
        creationflags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
        self.proc = subprocess.Popen(
            cmd,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            bufsize=0,
            creationflags=creationflags,
        )
        self._stderr_buffer.clear()
        self._stderr_stop.clear()
        self.last_stderr = ""
        self._first_frame_start = time.time()

        if not self.proc or getattr(self.proc, "stdout", None) is None:
            self.last_status = "error"
            self.last_error = (
                "process not started" if not self.proc else "process missing stdout"
            )
            self.logger.error(
                "FFmpeg start failed: {} ({})", self.pipeline, self.last_error
            )
            self.last_command = self.pipeline
            if self.proc:
                try:
                    self.proc.kill()
                except Exception:
                    pass
            self.proc = None
            self._stderr_thread = None
            return

        if getattr(self.proc, "stderr", None):

            def _drain() -> None:
                while not self._stderr_stop.is_set():
                    try:
                        line = self.proc.stderr.readline()
                    except Exception:
                        break
                    if not line:
                        break
                    self._stderr_buffer.append(
                        line.decode("utf-8", errors="ignore").rstrip()
                    )

            self._stderr_thread = threading.Thread(target=_drain, daemon=True)
            self._stderr_thread.start()
        else:
            self._stderr_thread = None
        self.last_status = "ok"
        self.last_error = ""

    # Internal -----------------------------------------------------------------
    # _init_stream routine
    def _init_stream(self) -> None:
        try:
            self._start_process()
        except Exception as e:
            # capture failures so callers can report the command
            self.last_status = "error"
            self.last_error = str(e)
            self.logger.error("FFmpeg start failed: {} ({})", self.pipeline, e)
            self.last_command = self.pipeline
            self.proc = None

    def _read_full_frame(self) -> bytes | None:
        """Read exactly one frame from the FFmpeg stdout pipe."""
        proc = self.proc
        if proc is None or getattr(proc, "stdout", None) is None:
            return None
        buffer = b""
        while len(buffer) < self.frame_size:
            stdout = getattr(proc, "stdout", None)
            if stdout is None or proc.poll() is not None:
                return None
            try:
                chunk = stdout.read(self.frame_size - len(buffer))
            except AttributeError:
                return None
            if not chunk:
                return None
            buffer += chunk
        return buffer

    def _next_transport(self) -> bool:
        """Switch to the next transport if available."""
        if self._transport_index + 1 >= len(self.retry_transports):
            return False
        self._transport_index += 1
        self.transport = self.retry_transports[self._transport_index]
        self._log_retry()
        self._release_stream()
        try:
            self._start_process()
        except Exception as e:
            self.logger.error("FFmpeg retry failed: {}", e)
            return False
        return True

    # _read_frame routine
    def _read_frame(self) -> Tuple[bool, Optional[np.ndarray]]:
        if (
            not self.initialized
            and time.time() - self._first_frame_start > self.first_frame_timeout
        ):
            if self._next_transport():
                return False, None
        if (
            self.proc is None
            or getattr(self.proc, "stdout", None) is None
            or self.proc.poll() is not None
        ):
            self._log_failure("process not running")
            if not self.running:
                return False, None
            self._log_retry()
            time.sleep(self.reconnect_delay)
            try:
                self._start_process()
            except Exception as e:
                self.logger.error("FFmpeg start failed: {} ({})", self.pipeline, e)
                self.last_status = "error"
                self.last_error = str(e)
                time.sleep(self.reconnect_delay)
            return False, None
        for _ in range(self.frame_skip - 1):
            if self._read_full_frame() is None:
                self._log_failure("short read")
                if not self.running:
                    return False, None
                self._log_retry()
                time.sleep(self.reconnect_delay)
                try:
                    self._start_process()
                except Exception as e:
                    self.logger.error("FFmpeg start failed: {} ({})", self.pipeline, e)
                    self.last_status = "error"
                    self.last_error = str(e)
                    time.sleep(self.reconnect_delay)
                return False, None
        raw = self._read_full_frame()
        if raw is None or len(raw) < self.frame_size:
            self._log_failure("short read")
            if not self.running:
                return False, None
            self._log_retry()
            time.sleep(self.reconnect_delay)
            try:
                self._start_process()
            except Exception as e:
                self.logger.error("FFmpeg start failed: {} ({})", self.pipeline, e)
                self.last_status = "error"
                self.last_error = str(e)
                time.sleep(self.reconnect_delay)
            return False, None
        try:
            frame = np.frombuffer(raw, dtype="uint8").reshape(
                self.height, self.width, self.channels
            )
        except ValueError:
            self._log_failure("reshape failed")
            return False, None

        if self.dup_filter and self.dup_filter.is_duplicate(frame):
            return False, None

        if self._successful_transport is None:
            self._successful_transport = self.transport
            err = "\n".join(self._stderr_buffer).strip()
            if err:
                self.logger.info(
                    "First frame received via {} (stderr: {})",
                    self.transport,
                    err,
                )
            else:
                self.logger.info("First frame received via {}", self.transport)
        return True, frame

    # wait_first_frame routine
    def wait_first_frame(self, timeout: float) -> np.ndarray:
        """Block until the first frame is read or ``timeout`` seconds elapse."""
        deadline = time.time() + timeout
        while time.time() < deadline:
            raw = self._read_full_frame()
            if raw:
                try:
                    frame = np.frombuffer(raw, dtype="uint8").reshape(
                        self.height, self.width, 3
                    )
                    if self._successful_transport is None:
                        self._successful_transport = self.transport
                    err = "\n".join(self._stderr_buffer).strip()
                    if err:
                        self.logger.info(
                            "First frame received via {} (stderr: {})",
                            self.transport,
                            err,
                        )
                    else:
                        self.logger.info("First frame received via {}", self.transport)
                    return frame
                except ValueError:
                    self._log_failure("reshape failed")
                    break
            if self.proc is None or self.proc.poll() is not None:
                self._log_failure("process not running")
                break
            time.sleep(0.01)
        self._release_stream()
        stderr_tail = "\n".join(self._stderr_buffer)
        self.last_status = "timeout"
        self.last_error = "no frame received"
        self.last_stderr = stderr_tail
        raise RuntimeError(
            f"Timeout waiting for first frame from {self.url}. "
            f"FFmpeg stderr tail:\n{stderr_tail}"
        )

    def _log_failure(self, reason: str) -> None:
        if not self.proc:
            return
        err = "\n".join(self._stderr_buffer)
        status = "error"
        message = reason or "unknown error"
        hint = ""
        if err.strip():
            err_lower = err.lower()
            for pat, (code, msg, h) in ERROR_PATTERNS.items():
                if pat.lower() in err_lower:
                    status = code
                    message = msg
                    hint = h
                    break
        self.logger.error("FFmpeg {}. cmd: {}", reason, self.pipeline)

        if err.strip():
            self.logger.error("FFmpeg stderr: {}", err.strip())
        if status != "error":
            self.logger.error("FFmpeg detected {}: {}", status, message)
        self.last_status = status
        self.last_error = message
        self.last_hint = hint
        self.last_stderr = err
        self.last_command = self.pipeline

        if status == "network":
            self.network_error_count += 1
            if self.network_error_count >= self.network_error_threshold:
                self.logger.error(
                    "Network error threshold reached for {}:{}; stopping stream",
                    self._ip,
                    self._port,
                )
                self.running = False
                self._release_stream()
        else:
            self.network_error_count = 0

    def _log_retry(self) -> None:
        err = "\n".join(self._stderr_buffer).strip()
        if err:
            self.logger.warning(
                "Retrying FFmpeg with {} (stderr: {})", self.transport, err
            )
        else:
            self.logger.warning("Retrying FFmpeg with {}", self.transport)

    # _release_stream routine
    def _release_stream(self) -> None:
        if self.proc:
            self.proc.kill()
        self._stderr_stop.set()
        if self._stderr_thread and self._stderr_thread.is_alive():
            self._stderr_thread.join(timeout=0.1)
        self._stderr_thread = None
        self.proc = None
        self.frames.clear()

    # read routine
    def read(self) -> Tuple[bool, Optional[np.ndarray]]:
        if self.queue:
            return super().read()
        return self._read_frame()

    @property
    def stderr(self) -> str:
        """Return collected FFmpeg stderr output."""
        return "\n".join(self._stderr_buffer)

    @property
    def successful_transport(self) -> str | None:
        """Return the transport that eventually produced frames."""
        return self._successful_transport
