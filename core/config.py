"""Configuration loading and saving utilities.

The :func:`save_config` helper serializes access to the configuration file
using a module-level :class:`threading.Lock` and an OS-level advisory lock.
Callers should **always** use :func:`save_config` instead of writing to the
file directly to avoid race conditions.
"""

from __future__ import annotations

import copy
import json
import os
import tempfile
import threading
from pathlib import Path
from typing import Any

import redis

try:
    import fcntl
except ImportError:  # pragma: no cover - Windows doesn't provide fcntl
    fcntl = None

# Guard against concurrent writes to the configuration file. All callers
# invoke :func:`save_config`, which acquires this lock before writing.
SAVE_CONFIG_LOCK = threading.Lock()

MODEL_CLASSES = [
    "no_dust_mask",
    "no_face_shield",
    "no_helmet",
    "no_protective_gloves",
    "no_safety_glasses",
    "no_safety_shoes",
    "no_vest_jacket",
    "helmet",
    "person",
    "person_smoking",
    "person_using_phone",
    "protective_gloves",
    "safety_glasses",
    "safety_shoes",
    "smoke",
    "sparks",
    "vest_jacket",
    "worker",
]

# PPE presence classes users can select.
PPE_ITEMS = [
    "helmet",
    "vest_jacket",
    "safety_shoes",
    "protective_gloves",
    "face_shield",
    "dust_mask",
    "safety_glasses",
]

# Mapping of presence class -> absence counterpart
PPE_PAIRS = {
    "helmet": "no_helmet",
    "vest_jacket": "no_vest_jacket",
    "safety_shoes": "no_safety_shoes",
    "protective_gloves": "no_protective_gloves",
    "face_shield": "no_face_shield",
    "dust_mask": "no_dust_mask",
    "safety_glasses": "no_safety_glasses",
}
# Task list containing both presence and absence PPE classes.
PPE_TASKS = list(PPE_PAIRS.keys()) + list(PPE_PAIRS.values())
ANOMALY_ITEMS = [
    "no_helmet",
    "no_safety_shoes",
    "no_safety_glasses",
    "no_protective_gloves",
    "no_dust_mask",
    "no_face_shield",
    "no_vest_jacket",
    "smoke",
    "sparks",
    "yellow_alert",
    "red_alert",
]
# Non-PPE classes grouped under "other" for simple monitoring
OTHER_CLASSES = [
    "person",
    "person_smoking",
    "person_using_phone",
    "smoke",
    "sparks",
    "worker",
    "fire",
]

COUNT_GROUPS = {
    "person": ["person"],
    "vehicle": ["car", "truck", "bus", "motorcycle", "bicycle"],
    "other": OTHER_CLASSES,
}
AVAILABLE_CLASSES = (
    MODEL_CLASSES + ANOMALY_ITEMS + [c for cl in COUNT_GROUPS.values() for c in cl]
)
# Camera task options. Counting directions are now defined as tasks and
# can be combined with PPE detection tasks. PPE tasks are expanded into
# their presence/absence pairs so callers don't have to worry about the
# mapping order when importing this module.
CAMERA_TASKS = ["in_count", "out_count", "full_monitor", "visitor_mgmt"] + MODEL_CLASSES

# Tasks shown on the camera page UI (only PPE-related classes). Defined
# after ``PPE_TASKS`` to avoid NameError on older Python versions where
# module-level forward references are not allowed.
UI_CAMERA_TASKS = ["in_out_counting", "visitor_mgmt"] + PPE_TASKS

# Default configuration values for :func:`load_config`.
CONFIG_DEFAULTS = {
    "track_ppe": [],
    "alert_anomalies": [],
    "track_objects": ["person"],
    "helmet_conf_thresh": 0.5,
    "detect_helmet_color": False,
    "show_lines": True,
    "show_ids": True,
    "show_counts": False,
    "preview_anomalies": [],
    "email_enabled": True,
    "show_track_lines": False,
    "preview_scale": 1.0,
    "enable_live_charts": True,
    "chart_update_freq": 5,
    "capture_buffer_seconds": 15,
    "frame_skip": 3,
    "detector_fps": 10,
    "adaptive_skip": False,
    "ffmpeg_flags": "-flags low_delay -fflags nobuffer",
    "enable_profiling": False,
    "enable_person_tracking": True,
    "profiling_interval": 5,
    "ppe_log_limit": 1000,
    "alert_key_retention_secs": 7 * 24 * 60 * 60,
    "ppe_log_retention_secs": 7 * 24 * 60 * 60,
    "pipeline_profiles": {},
    "ffmpeg_high_watermark": 0,
    "ffmpeg_low_watermark": 0,
    "ffmpeg_supports_drop": False,
    "cpu_limit_percent": 50,
    "max_retry": 5,
    "capture_buffer": 3,
    "local_buffer_size": 1,
    "person_model": "yolov8n.pt",
    "ppe_model": "mymodalv7.pt",
    "license_key": "TRIAL-123456",
    "max_cameras": 3,
    "features": {
        "in_out_counting": True,
        "ppe_detection": True,
        "visitor_mgmt": False,
        "face_recognition": False,
    },
    "visitor_model": "buffalo_l",
    "face_match_thresh": 0.6,
    "visitor_conf_thresh": 0.85,
    "visitor_sim_thresh": 0.85,
    "visitor_min_face_size": 80,
    "visitor_blur_thresh": 150,
    "visitor_size_thresh": 10000,
    "visitor_fps_skip": 2,
    "show_face_boxes": False,
    "debug_logs": False,
    "enable_face_recognition": True,
    "enable_face_counting": False,
    "face_count_conf": 0.85,
    "face_count_similarity": 0.6,
    "face_count_min_size": 80,
    "logo_url": "https://www.coromandel.biz/wp-content/uploads/2025/04/cropped-CIL-Logo_WB-02-1-300x100.png",
    "logo2_url": "https://www.coromandel.biz/wp-content/uploads/2025/02/murugappa-logo.png",
    "users": [
        {"username": "admin", "password": "rapidadmin", "role": "admin"},
        {"username": "viewer", "password": "viewer", "role": "viewer"},
    ],
    "settings_password": "000",
}


__all__ = [
    "MODEL_CLASSES",
    "PPE_ITEMS",
    "PPE_PAIRS",
    "PPE_TASKS",
    "ANOMALY_ITEMS",
    "OTHER_CLASSES",
    "COUNT_GROUPS",
    "AVAILABLE_CLASSES",
    "CAMERA_TASKS",
    "UI_CAMERA_TASKS",
    "CONFIG_DEFAULTS",
    "sync_detection_classes",
    "load_config",
    "save_config",
    "load_branding",
    "save_branding",
]


def _sanitize_track_ppe(items: list[str]) -> list[str]:
    """Normalize PPE items to their base names.

    Any ``no_`` prefixes or minor formatting differences are stripped so that
    the returned list only contains valid presence classes from
    :data:`PPE_ITEMS`.
    """

    cleaned: list[str] = []
    for raw in items:
        base = raw.lower().replace(" ", "_").replace("-", "_").replace("/", "_")
        while base.startswith("no_"):
            base = base[3:]
        if base in PPE_ITEMS and base not in cleaned:
            cleaned.append(base)
    return cleaned


# Internal helpers --------------------------------------------------------


def _read_config_file(path: str) -> dict:
    """Read a JSON configuration file from ``path``."""

    if not os.path.exists(path):
        raise FileNotFoundError(path)
    with open(path) as f:
        return json.load(f)


def _apply_defaults(data: dict) -> dict:
    """Populate missing configuration keys and normalize fields."""

    for key, value in CONFIG_DEFAULTS.items():
        if isinstance(value, (dict, list)):
            data.setdefault(key, copy.deepcopy(value))
        else:
            data.setdefault(key, value)
    raw_ppe = data.get("track_ppe", [])
    data["track_ppe"] = _sanitize_track_ppe(raw_ppe)
    data["stream_mode"] = "ffmpeg"
    default_priority = ["ffmpeg", "gstreamer", "opencv"]
    priority = data.get("backend_priority", default_priority)
    if isinstance(priority, str):
        priority = [priority]
    data["backend_priority"] = ["ffmpeg"] + [b for b in priority if b != "ffmpeg"]
    return data


def _rewrite_pipelines(data: dict) -> None:
    """Upgrade legacy pipeline configuration in-place."""

    profiles = data["pipeline_profiles"]
    for _, cfg in profiles.items():
        if "pipelines" not in cfg:
            extra = cfg.pop("extra_pipeline", None)
            flags = cfg.pop("ffmpeg_flags", None)
            base_gst = (
                'rtspsrc location="{url}" protocols=tcp latency=100 ! '
                "rtph264depay ! h264parse ! avdec_h264 ! videoconvert"
            )
            if extra:
                base_gst += f" ! {extra}"
            base_gst += (
                " ! video/x-raw,format=BGR ! queue max-size-buffers=1 "
                "leaky=downstream ! appsink name=appsink drop=true "
                "sync=false max-buffers=1"
            )
            base_ffmpeg = "ffmpeg -rtsp_transport tcp -i {url}"
            if flags:
                base_ffmpeg += f" {flags}"
            base_ffmpeg += " -f rawvideo -pix_fmt bgr24 -"
            cfg["pipelines"] = {
                "gstreamer": base_gst,
                "ffmpeg": base_ffmpeg,
                "opencv": "{url}",
            }
        pipes = cfg.setdefault("pipelines", {})
        pipes.setdefault("gstreamer", "")
        pipes.setdefault("ffmpeg", "")
        pipes.setdefault("opencv", "{url}")


def _load_branding_file(path: str) -> dict:
    """Load branding information from ``path``."""

    return load_branding(path)


def _persist_to_redis(data: dict, redis_client: redis.Redis | None) -> None:
    """Store ``data`` in ``redis_client`` if provided."""

    if redis_client is not None:
        redis_client.set("config", json.dumps(data))


# sync_detection_classes routine
def sync_detection_classes(cfg: dict) -> None:
    object_classes: list[str] = []
    count_classes: list[str] = []
    for group in cfg.get("track_objects", ["person"]):
        count_classes.extend(COUNT_GROUPS.get(group, [group]))
    object_classes.extend(count_classes)

    base_items = _sanitize_track_ppe(cfg.get("track_ppe", []))
    detection_items: list[str] = []
    for item in base_items:
        if item not in AVAILABLE_CLASSES:
            continue
        detection_items.append(item)
        pair = PPE_PAIRS.get(item)
        if pair and pair in AVAILABLE_CLASSES:
            detection_items.append(pair)

    cfg["track_ppe"] = base_items
    cfg["ppe_classes"] = detection_items
    cfg["object_classes"] = object_classes + detection_items
    cfg["count_classes"] = count_classes


# load_config routine
def load_config(
    path: str,
    r: redis.Redis | None,
    *,
    data: dict | None = None,
    minimal: bool = False,
) -> dict:
    """Load configuration from ``path``.

    If ``minimal`` is ``True``, the configuration file is parsed and a
    dictionary containing the ``redis_url`` and raw data is returned without
    applying defaults or touching Redis.  This allows callers to obtain
    connection information without opening the file again.

    When ``data`` is provided, it is used instead of reading from ``path`` so
    the file is parsed only once.
    """

    if data is None:
        data = _read_config_file(path)

    if minimal:
        redis_url = data.get("redis_url")
        if not redis_url:
            raise KeyError("redis_url is required")
        return {"redis_url": redis_url, "data": data}
    if not data.get("redis_url"):
        raise KeyError("redis_url is required")
    data = _apply_defaults(data)
    _rewrite_pipelines(data)
    branding_path = str(Path(path).with_name("branding.json"))
    data.setdefault("branding", _load_branding_file(branding_path))
    sync_detection_classes(data)
    _persist_to_redis(data, r)
    return data


# save_config routine
def save_config(cfg: dict, path: str, r: redis.Redis) -> None:
    """Persist configuration to disk and update Redis atomically.

    The function serializes writes using :data:`SAVE_CONFIG_LOCK` and an
    advisory OS-level lock via :func:`fcntl.flock` to guard against
    concurrent writes from other processes.
    """

    raw_ppe = cfg.get("track_ppe", [])
    cfg["track_ppe"] = _sanitize_track_ppe(raw_ppe)
    sync_detection_classes(cfg)

    frame_skip = cfg.get("frame_skip", 3)
    if not isinstance(frame_skip, int) or frame_skip < 0:
        raise ValueError("frame_skip must be a non-negative integer")
    cfg["frame_skip"] = frame_skip
    detector_fps = cfg.get("detector_fps", 10)
    if not isinstance(detector_fps, (int, float)) or detector_fps < 0:
        raise ValueError("detector_fps must be non-negative")
    cfg["detector_fps"] = detector_fps
    cfg["adaptive_skip"] = bool(cfg.get("adaptive_skip", False))
    cfg.setdefault("ffmpeg_flags", "-flags low_delay -fflags nobuffer")

    device = cfg.get("device")
    if device is not None and not isinstance(device, str):
        cfg["device"] = str(device)

    # _ser routine
    def _ser(o: Any):
        import datetime as _dt
        import enum
        import uuid
        from pathlib import Path

        try:
            import torch  # type: ignore
        except ImportError:  # pragma: no cover - torch is optional
            torch = None

        if isinstance(o, Path):
            return str(o)
        if torch is not None and isinstance(o, torch.device):
            return str(o)
        if isinstance(o, (enum.Enum, uuid.UUID, _dt.datetime, _dt.date)):
            return str(o)
        raise TypeError(str(o))

    with SAVE_CONFIG_LOCK:
        with open(path, "a+") as f:
            if fcntl is not None:
                fcntl.flock(f, fcntl.LOCK_EX)
            try:
                f.seek(0)
                f.truncate()
                json.dump(cfg, f, indent=2, default=_ser)
                f.flush()
                os.fsync(f.fileno())
            finally:
                if fcntl is not None:
                    fcntl.flock(f, fcntl.LOCK_UN)
        r.set("config", json.dumps(cfg, default=_ser))


# Branding config -----------------------------------------------------------

BRANDING_DEFAULTS = {
    "company_name": "My Company",
    "site_name": "Main Site",
    "website": "",
    "address": "",
    "phone": "",
    "tagline": "",
    "watermark": False,
    "print_layout": "A5",
    "company_logo": "",
    "company_logo_url": "",
    "footer_logo": "",
    "footer_logo_url": "",
}


# load_branding routine
def load_branding(path: str) -> dict:
    """Load branding configuration from a JSON file."""
    if os.path.exists(path):
        with open(path) as f:
            data = json.load(f)
    else:
        data = {}
    for k, v in BRANDING_DEFAULTS.items():
        data.setdefault(k, v)
    return data


# save_branding routine
def save_branding(data: dict, path: str) -> None:
    """Save branding configuration."""
    dir_name = os.path.dirname(path)
    fd, tmp_path = tempfile.mkstemp(dir=dir_name or ".")
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(data, f, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, path)
    finally:
        try:
            os.remove(tmp_path)
        except FileNotFoundError:
            pass
