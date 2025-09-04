"""Factory helpers for opening camera streams."""

import json
import shlex
import time
from typing import Any

import ffmpeg
import redis
from loguru import logger

from config import config as shared_config
from utils.redis import get_camera_overrides_sync, get_sync_client
from utils.url import get_stream_type
from utils.video import get_stream_resolution

from .ffmpeg_stream import FFmpegCameraStream
from .gstreamer_stream import GstCameraStream
from .opencv_stream import OpenCVCameraStream
from .stream_probe import probe_stream

logger = logger.bind(module="camera_factory")


# Redis client is set by tracker_manager when trackers start
redis_client: redis.Redis | None = None


class StreamUnavailable(Exception):
    """Raised when no capture backend can provide frames."""


__all__ = ["open_capture", "StreamUnavailable"]


def _apply_defaults(shared_cfg: dict[str, Any], overrides: dict[str, str]) -> dict:
    """Return runtime parameters merged from config and overrides."""

    def _to_int(value, default):
        try:
            return int(value)
        except (TypeError, ValueError):
            return default

    def _to_float(value, default=None):
        if value is None:
            return default
        try:
            return float(value)
        except (TypeError, ValueError):
            return default

    params = {
        "ready_frames": _to_int(shared_cfg.get("ready_frames"), 1),
        "ready_duration": _to_float(shared_cfg.get("ready_duration")),
        "ready_timeout": _to_float(shared_cfg.get("ready_timeout"), 15.0),
        "ffmpeg_reconnect_delay": _to_float(
            shared_cfg.get("ffmpeg_reconnect_delay"), 1.0
        ),
        "local_buffer_size": _to_int(shared_cfg.get("local_buffer_size"), 1),
    }
    for key in ("ready_frames", "ready_duration", "ready_timeout"):
        if overrides.get(key) is not None:
            try:
                cast = int if key == "ready_frames" else float
                params[key] = cast(overrides[key])
            except (TypeError, ValueError):
                pass
    return params


def _probe_stream(src, use_gpu: bool) -> dict | None:
    """Return probe summary for *src* if possible."""

    try:
        return probe_stream(src, sample_seconds=1, enable_hwaccel=use_gpu)
    except Exception:
        return None


def _build_backend_chain(stream_mode: str | None, profile_cfg: dict) -> list[str]:
    """Return backend priority list derived from mode or profile."""

    backend = profile_cfg.get("backend")
    if backend:
        return [backend]
    if stream_mode == "gstreamer":
        return ["gstreamer", "ffmpeg", "opencv"]
    if stream_mode == "opencv":
        return ["opencv"]
    return ["ffmpeg", "opencv"]


def _spawn_backend(backend: str, params: dict) -> "CameraStream":
    """Instantiate a backend capture based on *backend* and *params*."""

    if backend == "gstreamer":
        return GstCameraStream(
            params["src"],
            params["width"],
            params["height"],
            rtsp_transport=params["rtsp_transport"],
            use_gpu=params["use_gpu"],
            buffer_size=params["capture_buffer"],
            pipeline=params.get("pipeline"),
            cam_id=params["cam_id"],
        )
    if backend == "ffmpeg":
        return FFmpegCameraStream(
            params["src"],
            params["width"],
            params["height"],
            transport=params["rtsp_transport"],
            buffer_size=params["capture_buffer"],
            extra_flags=params.get("extra_flags", []),
            reconnect_delay=params["ffmpeg_reconnect_delay"],
            command=params.get("pipeline"),
            cam_id=params["cam_id"],
            mirror=params.get("mirror", False),
            orientation=params.get("orientation", "vertical"),
        )
    if backend in {"opencv", "cv2"}:
        source = params.get("pipeline") or params["src"]
        return OpenCVCameraStream(
            source,
            params["width"],
            params["height"],
            buffer_size=params["capture_buffer"],
            cam_id=params["cam_id"],
        )
    raise ValueError(f"Unknown backend: {backend}")


def _init_debug(cam_id: int):
    """Return (debug_key, debug_data) for *cam_id*."""

    if redis_client is None:
        return None, {"attempts": []}
    key = f"camera_debug:{cam_id}"
    data: dict[str, Any] = {"attempts": []}
    try:
        existing = redis_client.get(key)
        if existing:
            text = (
                existing.decode()
                if isinstance(existing, (bytes, bytearray))
                else existing
            )
            try:
                parsed = json.loads(text)
                if isinstance(parsed, dict):
                    data = parsed
                    data.setdefault("attempts", [])
                else:
                    data = {"attempts": [], "summary": text}
            except Exception:
                data = {"attempts": [], "summary": text}
    except Exception:
        data = {"attempts": []}
    return key, data


def _append_debug(debug_key, debug_data, backend: str, msg: str, cap=None) -> None:
    if not debug_key or redis_client is None:
        return
    entry = {"backend": backend, "error": msg}
    if cap is not None:
        cmd = getattr(cap, "pipeline", None) or getattr(cap, "cmd", None)
        if isinstance(cmd, list):
            cmd = " ".join(cmd)
        if cmd:
            if backend == "gstreamer":
                entry["pipeline"] = cmd
            else:
                entry["command"] = cmd
    debug_data.setdefault("attempts", []).append(entry)
    try:
        redis_client.set(debug_key, json.dumps(debug_data))
    except Exception:
        pass


def _clear_debug(debug_key, debug_data) -> None:
    if not debug_key or redis_client is None:
        return
    if "probe" in debug_data:
        try:
            redis_client.set(debug_key, json.dumps({"probe": debug_data["probe"]}))
        except Exception:
            pass
    else:
        redis_client.delete(debug_key)


# open_capture routine
def open_capture(
    src,
    cam_id,
    src_type: str | None = None,
    resolution: str = "original",
    rtsp_transport: str = "tcp",
    stream_mode: str = "ffmpeg",
    use_gpu: bool = True,
    capture_buffer: int = 3,
    local_buffer_size: int | None = None,
    backend_priority: list[str] | str | None = None,
    ffmpeg_flags: list[str] | str | None = None,
    pipeline: str | None = None,
    profile: str | None = None,
    ffmpeg_reconnect_delay: float | None = None,
    ready_frames: int | None = None,
    ready_duration: float | None = None,
    ready_timeout: float | None = None,
    for_display: bool = False,
    reverse: bool = False,
    orientation: str = "vertical",
):
    """Return a capture object for the configured stream."""

    global redis_client
    res_map = {"480p": (640, 480), "720p": (1280, 720), "1080p": (1920, 1080)}
    width = height = None
    if resolution != "original":
        if "x" in resolution:
            try:
                width, height = [int(v) for v in resolution.lower().split("x", 1)]
            except Exception:
                width = height = None
        if width is None or height is None:
            width, height = res_map.get(resolution, (None, None))

    if isinstance(src, str):
        src = src.strip()

    if redis_client is None:
        try:
            redis_client = get_sync_client()
        except Exception:
            redis_client = None

    overrides: dict[str, str] = {}
    if redis_client:
        try:
            overrides = get_camera_overrides_sync(redis_client, cam_id) or {}
        except Exception:
            overrides = {}

    params = _apply_defaults(shared_config, overrides)
    if ready_frames is not None:
        params["ready_frames"] = ready_frames
    if ready_duration is not None:
        params["ready_duration"] = ready_duration
    if ready_timeout is not None:
        params["ready_timeout"] = ready_timeout
    if ffmpeg_reconnect_delay is not None:
        params["ffmpeg_reconnect_delay"] = ffmpeg_reconnect_delay
    if local_buffer_size is not None:
        params["local_buffer_size"] = local_buffer_size

    debug_key, debug_data = _init_debug(cam_id)
    attempt_msgs: list[str] = []
    log = logger.bind(cam_id=cam_id)

    url_override = overrides.get("url")
    if url_override:
        src = url_override.strip()
    if src_type is None:
        src_type = get_stream_type(src)

    probe_summary: dict[str, Any] | None = None
    if src_type == "rtsp":
        try:
            info = ffmpeg.probe(src)
            streams = info.get("streams", [])
            video = next((s for s in streams if s.get("codec_type") == "video"), {})
            log.info(
                "ffprobe: codec={} resolution={}x{}",
                video.get("codec_name"),
                video.get("width"),
                video.get("height"),
            )
        except ffmpeg.Error as e:
            err = (
                e.stderr.decode("utf-8", errors="ignore")
                if isinstance(e.stderr, (bytes, bytearray))
                else str(e)
            )
            log.warning("ffprobe error: {}", err)
        probe_summary = _probe_stream(src, use_gpu)
        if probe_summary:
            rtsp_transport = probe_summary.get("transport", rtsp_transport)
            use_gpu = probe_summary.get("hwaccel", use_gpu)
            if debug_key:
                meta = probe_summary.get("metadata", {})
                debug_data["probe"] = {
                    "codec": meta.get("codec"),
                    "resolution": f"{meta.get('width')}x{meta.get('height')}",
                    "nominal_fps": meta.get("fps"),
                    "effective_fps": probe_summary.get("effective_fps"),
                    "transport": probe_summary.get("transport"),
                    "hwaccel": probe_summary.get("hwaccel"),
                }
                try:
                    redis_client.set(debug_key, json.dumps(debug_data))
                except Exception:
                    pass

    profile = profile or overrides.get("profile")
    profiles = shared_config.get("pipeline_profiles", {})
    profile_cfg = profiles.get(profile, {}) if profile else {}
    profile_pipelines = profile_cfg.get("pipelines", {})

    if resolution == "original" and profile_cfg.get("resolution"):
        resolution = profile_cfg["resolution"]
        if "x" in resolution:
            try:
                width, height = [int(v) for v in resolution.lower().split("x", 1)]
            except Exception:
                width = height = None
        if width is None or height is None:
            width, height = res_map.get(resolution, (None, None))

    if resolution == "original" and (width is None or height is None):
        width, height = get_stream_resolution(src)

    if backend_priority is None:
        backend_priority = _build_backend_chain(stream_mode, profile_cfg)
    elif isinstance(backend_priority, str):
        backend_priority = [backend_priority]
    else:
        backend_priority = list(backend_priority)

    backend_override = overrides.get("backend")
    if backend_override:
        backend_priority = [backend_override]
    if not shared_config.get("enable_gstreamer", False):
        backend_priority = [b for b in backend_priority if b != "gstreamer"]
    if not for_display:
        backend_priority = [b for b in backend_priority if b != "opencv"]

    extra_flags: list[str] = []
    if ffmpeg_flags:
        log.info("ffmpeg flags: {}", ffmpeg_flags)
        if isinstance(ffmpeg_flags, str):
            try:
                extra_flags = shlex.split(ffmpeg_flags)
            except ValueError:
                log.error("invalid ffmpeg flags: {}", ffmpeg_flags)
                extra_flags = []
        else:
            extra_flags = list(ffmpeg_flags)

    if src_type == "local":
        try:
            index = int(src) if str(src).isdigit() else src
        except ValueError:
            index = src
        cap = OpenCVCameraStream(
            index, width, height, buffer_size=params["local_buffer_size"], cam_id=cam_id
        )
        log.bind(backend="opencv", url=src, cmd=str(index), stderr="").info(
            "Attempting OpenCVCameraStream (local)"
        )
        start = time.time()
        ready = False
        while time.time() - start < params["ready_timeout"]:
            if cap.isOpened():
                ret, frame = cap.read_latest()
                if ret and frame is not None:
                    ready = True
                    break
            time.sleep(0.1)
        if not ready:
            cap.release()
            msg = "OpenCV local stream failed: no frames from local device"
            log.error(msg)
            raise StreamUnavailable(msg)
        log.info("Using OpenCVCameraStream (local)")
        if not attempt_msgs:
            _clear_debug(debug_key, debug_data)
        return cap, rtsp_transport

    def _ready(capture, required_frames, stable_duration, timeout) -> bool:
        start = time.time()
        consecutive = 0
        stable_start: float | None = None
        while time.time() - start < timeout:
            if not capture.isOpened():
                time.sleep(0.1)
                continue
            ret, frame = capture.read_latest()
            now = time.time()
            if ret and frame is not None:
                consecutive += 1
                if stable_start is None:
                    stable_start = now
                if (
                    stable_duration
                    and stable_start is not None
                    and now - stable_start >= stable_duration
                ):
                    return True
                if required_frames and consecutive >= required_frames:
                    return True
            else:
                consecutive = 0
                stable_start = None
            time.sleep(0.1)
        capture.release()
        return False

    for mode in backend_priority:
        cap = None
        try:
            tmpl = (
                pipeline
                if pipeline is not None
                else overrides.get("pipeline") or profile_pipelines.get(mode)
            )
            if mode == "ffmpeg" and pipeline is None and tmpl is None:
                tmpl = (
                    "ffmpeg -rtsp_transport tcp -i {url} -f rawvideo -pix_fmt bgr24 -"
                )
            custom_pipeline = tmpl.format(url=src) if tmpl else None
            if custom_pipeline:
                log.info("custom {} pipeline: {}", mode, custom_pipeline)
            spawn_params = {
                "src": src,
                "width": width,
                "height": height,
                "rtsp_transport": rtsp_transport,
                "use_gpu": use_gpu,
                "capture_buffer": capture_buffer,
                "pipeline": custom_pipeline,
                "cam_id": cam_id,
                "extra_flags": extra_flags if custom_pipeline is None else [],
                "ffmpeg_reconnect_delay": params["ffmpeg_reconnect_delay"],
                "mirror": reverse,
                "orientation": orientation,
            }
            cap = _spawn_backend(mode, spawn_params)
            if mode == "ffmpeg":
                try:
                    (
                        ffmpeg.input(src, rtsp_transport=rtsp_transport)
                        .output("pipe:", vframes=1, format="rawvideo")
                        .run(capture_stdout=True, capture_stderr=True)
                    )
                    log.info("ffmpeg single-frame check succeeded")
                except ffmpeg.Error as e:
                    err = (
                        e.stderr.decode("utf-8", errors="ignore")
                        if isinstance(e.stderr, (bytes, bytearray))
                        else str(e)
                    )
                    log.warning("ffmpeg single-frame check failed: {}", err)
            if _ready(
                cap,
                params["ready_frames"],
                params["ready_duration"],
                params["ready_timeout"],
            ):
                name = "GStreamer" if mode == "gstreamer" else mode.capitalize()
                if not attempt_msgs:
                    _clear_debug(debug_key, debug_data)
                if mode == "ffmpeg":
                    used = getattr(cap, "successful_transport", None) or getattr(
                        cap, "transport", rtsp_transport
                    )
                    log.bind(backend=mode).info("Using FFmpegCameraStream ({})", used)
                    return cap, used
                log.bind(backend=mode).info("Using {}CameraStream", name)
                return cap, rtsp_transport
            cap.release()
            reason = getattr(cap, "last_error", None) or "no frames within timeout"
            name = "GStreamer" if mode == "gstreamer" else mode.capitalize()
            msg = f"{name} stream failed: {reason}"
            log.warning(msg)
            _append_debug(debug_key, debug_data, mode, msg, cap)
            attempt_msgs.append(msg)
        except Exception as e:
            name = "GStreamer" if mode == "gstreamer" else mode.capitalize()
            msg = f"{name} init error: {e}"
            log.error(msg)
            _append_debug(debug_key, debug_data, mode, msg, cap)
            attempt_msgs.append(msg)
    summary = "; ".join(attempt_msgs) if attempt_msgs else "no backends attempted"
    final_msg = f"Stream unavailable for {src}. Attempts: {summary}"
    log.error(final_msg)
    if debug_key:
        debug_data["summary"] = final_msg
        try:
            redis_client.set(debug_key, json.dumps(debug_data))
        except Exception:
            pass

    raise StreamUnavailable(final_msg)
