import json
import subprocess
import time
from dataclasses import dataclass
from itertools import product
from typing import Any, Dict, List


def _parse_ffprobe(text: str) -> Dict[str, Any]:
    try:
        info = json.loads(text)
    except Exception:
        return {}
    for stream in info.get("streams", []):
        if stream.get("codec_type") == "video":
            codec = stream.get("codec_name")
            profile = stream.get("profile")
            width = stream.get("width")
            height = stream.get("height")
            pix_fmt = stream.get("pix_fmt")
            bit_rate = stream.get("bit_rate")
            avg_rate = stream.get("avg_frame_rate")
            r_rate = stream.get("r_frame_rate")
            time_base = stream.get("time_base")
            fps_txt = r_rate or avg_rate or "0/1"
            try:
                num, den = fps_txt.split("/", 1)
                fps = float(num) / float(den)
            except Exception:
                fps = 0.0
            return {
                "codec": codec,
                "profile": profile,
                "width": width,
                "height": height,
                "pix_fmt": pix_fmt,
                "bit_rate": bit_rate,
                "avg_frame_rate": avg_rate,
                "r_frame_rate": r_rate,
                "time_base": time_base,
                "nominal_fps": fps,
            }
    return {}


@dataclass
class TrialResult:
    transport: str
    hwaccel: bool
    frames: int
    fps: float
    elapsed: float


# build ffmpeg trial command
def _build_trial_cmd(
    url: str, transport: str, hwaccel: bool, sample_seconds: int
) -> List[str]:
    cmd = ["ffmpeg", "-rtsp_transport", transport]
    if transport == "tcp":
        cmd += ["-rtsp_flags", "prefer_tcp"]
    if hwaccel:
        cmd += ["-hwaccel", "auto"]
    cmd += ["-i", url, "-t", str(sample_seconds), "-f", "null", "-"]
    return cmd


# probe_stream routine
def probe_stream(
    url: str, sample_seconds: int = 2, enable_hwaccel: bool = True
) -> Dict[str, Any]:
    """Probe a stream for metadata and effective FPS.

    This helper performs an ``ffprobe`` to gather codec and resolution
    information and runs short ``ffmpeg`` trials over different transports
    and hardware acceleration settings. The combination yielding the most
    decoded frames is selected.
    """

    meta: Dict[str, Any] = {}
    try:
        proc = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_streams",
                "-print_format",
                "json",
                url,
            ],
            capture_output=True,
            text=True,
            check=True,
            timeout=10,
        )
        meta = _parse_ffprobe(proc.stdout)
    except Exception:
        meta = {}

    transports = ["tcp", "udp"]
    hw_opts = [False, True] if enable_hwaccel else [False]

    def _run_trial(transport: str, hw: bool) -> TrialResult:
        cmd = _build_trial_cmd(url, transport, hw, sample_seconds)
        start = time.time()
        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                check=False,
                timeout=sample_seconds + 5,
            )
            duration = max(time.time() - start, 0.001)
            stderr = proc.stderr
            frames = 0
            for line in stderr.splitlines():
                line = line.strip()
                if line.startswith("frame="):
                    try:
                        frames = int(line.split()[0].split("=")[1])
                    except Exception:
                        frames = 0
            fps = frames / duration
        except Exception:
            duration = 0.0
            frames = 0
            fps = 0.0
        return TrialResult(transport, hw, frames, fps, duration)

    trials: List[TrialResult] = [
        _run_trial(transport, hw) for transport, hw in product(transports, hw_opts)
    ]

    best = max(
        trials,
        key=lambda t: (t.frames, t.fps),
        default=TrialResult("tcp", False, 0, 0.0, 0.0),
    )
    return {
        "metadata": meta,
        "transport": best.transport,
        "hwaccel": best.hwaccel,
        "frames": best.frames,
        "effective_fps": best.fps,
        "elapsed": best.elapsed,
        "trials": [t.__dict__ for t in trials],
    }


def _map_ffmpeg_error(stderr: str) -> str:
    """Map stderr output to a simplified error code."""

    s = stderr.lower()
    if "401" in s or "unauthor" in s:
        return "AUTH_FAILED"
    if "connection refused" in s:
        return "CONNECTION_REFUSED"
    if "404" in s or "not found" in s:
        return "RTSP_404"
    if "461" in s or "unsupported transport" in s:
        return "RTSP_461"
    if "timed out" in s or "timeout" in s:
        return "CONNECTION_TIMEOUT"
    return "UNKNOWN"


_ERROR_HINTS = {
    "BAD_URL": ["URL must start with rtsp:// or rtsps://"],
    "NO_VIDEO_STREAM": ["Ensure the stream provides a video track"],
    "AUTH_FAILED": ["Verify camera credentials"],
    "CONNECTION_REFUSED": ["Verify camera is reachable and port is open"],
    "RTSP_404": ["Check stream path or channel"],
    "RTSP_461": ["Camera rejected transport; try different RTSP protocol"],
    "CONNECTION_TIMEOUT": ["Check network connectivity or increase timeout"],
}


def check_rtsp(
    url: str,
    timeout_sec: float = 5.0,
    rtsp_transport: str = "tcp",
) -> Dict[str, Any]:
    """Perform a minimal RTSP probe returning metadata or an error code.

    The routine validates the URL, extracts basic metadata using ``ffprobe`` and
    attempts to read up to one second of data with FFmpeg. Errors are mapped to
    simplified codes with optional hints.
    """

    if not url.startswith(("rtsp://", "rtsps://")):
        return {
            "ok": False,
            "error": "BAD_URL",
            "hints": _ERROR_HINTS.get("BAD_URL"),
        }

    try:
        proc = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_streams",
                "-print_format",
                "json",
                url,
            ],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
        meta = _parse_ffprobe(proc.stdout)
    except Exception as e:  # pragma: no cover - unexpected failures
        return {"ok": False, "error": "FFPROBE_FAILED", "stderr_tail": str(e)}

    if not meta:
        return {
            "ok": False,
            "error": "NO_VIDEO_STREAM",
            "stderr_tail": "\n".join(proc.stderr.splitlines()[-20:]),
            "hints": _ERROR_HINTS.get("NO_VIDEO_STREAM"),
        }

    rw_timeout = int(timeout_sec * 1_000_000)
    cmd = [
        "ffmpeg",
        "-rtsp_transport",
        rtsp_transport,
        "-rw_timeout",
        str(rw_timeout),
        "-i",
        url,
        "-t",
        "1",
        "-f",
        "null",
        "-",
    ]

    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
        )
    except Exception as e:
        return {
            "ok": False,
            "error": "START_FAILED",
            "stderr_tail": str(e),
        }

    try:
        _, stderr = proc.communicate(timeout=timeout_sec + 5)
    except Exception:
        proc.kill()
        _, stderr = proc.communicate()
        return {
            "ok": False,
            "error": "READ_FAILED",
            "stderr_tail": "\n".join(stderr.splitlines()[-20:]),
        }
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.communicate()

    stderr_tail = "\n".join((stderr or "").splitlines()[-20:])
    if proc.returncode != 0:
        code = _map_ffmpeg_error(stderr)
        return {
            "ok": False,
            "error": code,
            "stderr_tail": stderr_tail,
            "hints": _ERROR_HINTS.get(code),
        }

    return {"ok": True, "meta": meta, "stderr_tail": stderr_tail}
