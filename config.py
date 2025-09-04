"""Application configuration and thresholds."""

from dataclasses import dataclass


@dataclass
class FaceThresholds:
    """Centralized face processing thresholds."""

    recognition_match: float = 0.6
    db_duplicate: float = 0.95
    duplicate_suppression: float = 0.5
    blur_detection: float = 100.0


FACE_THRESHOLDS = FaceThresholds()

DEFAULT_CONFIG = {
    "enable_person_tracking": True,
    "enable_face_recognition": True,
    "default_host": "",
    "camera_id": "",
    "license_info": {"features": {"face_recognition": True}},
    "features": {"face_recognition": True},
    # expose key for backward compatibility
    "face_match_thresh": FACE_THRESHOLDS.recognition_match,
    "local_buffer_size": 1,
    "model_version": 1,
    "preview_scale": 1.0,
    "detector_fps": 10,
    "adaptive_skip": False,
}

# Global configuration object to share across modules. Default settings may be
# injected at runtime by ``set_config``.
config = DEFAULT_CONFIG.copy()


# set_config routine
def set_config(cfg: dict) -> None:
    """Replace the global configuration with ``cfg``.

    Ensures required defaults like ``enable_person_tracking`` are present so
    callers can rely on them being available.
    """

    config.clear()
    config.update(DEFAULT_CONFIG)
    config.update(cfg)

    # Keep centralized thresholds in sync with overrides
    FACE_THRESHOLDS.recognition_match = config.get(
        "face_match_thresh", FACE_THRESHOLDS.recognition_match
    )
    FACE_THRESHOLDS.db_duplicate = config.get(
        "face_db_dup_thresh", FACE_THRESHOLDS.db_duplicate
    )
    FACE_THRESHOLDS.duplicate_suppression = config.get(
        "face_duplicate_thresh", FACE_THRESHOLDS.duplicate_suppression
    )
    FACE_THRESHOLDS.blur_detection = config.get(
        "blur_detection_thresh", FACE_THRESHOLDS.blur_detection
    )
