"""Worker thread for personal protective equipment detection."""

import json
import threading
import time
from pathlib import Path

import cv2
import psutil
from loguru import logger

from core import events
from modules.profiler import log_resource_usage, profile_predict, register_thread
from utils.gpu import get_device
from utils.redis import trim_sorted_set_sync

try:  # optional heavy dependency
    import torch  # type: ignore
except ModuleNotFoundError:  # pragma: no cover - optional in tests
    torch = None


# determine_status routine
def determine_status(scores: dict, item: str, thresh: float) -> tuple[str, float]:
    """Return (status, conf) based on detection scores."""
    key = item.lower().replace(" ", "_").replace("-", "_").replace("/", "_")
    while key.startswith("no_"):
        key = key[3:]
    pos_conf = scores.get(key, 0)
    neg_conf = scores.get(f"no_{key}", 0)
    if pos_conf >= thresh:
        return key, pos_conf
    return f"no_{key}", neg_conf


def _fetch_job(redis) -> dict | None:
    """Pull and decode a job from ``ppe_queue``."""
    res = redis.brpop("ppe_queue", timeout=1)
    if not res:
        return None
    _, raw = res
    try:
        return json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        return None


def _analyze_frame(img, model, cfg) -> dict[str, float]:
    """Run detection model on ``img`` and return score dict."""
    del cfg  # configuration unused but part of public signature
    res_det = profile_predict(
        model, "PPEWorker", img, device=getattr(model, "device", None), verbose=False
    )[0]
    scores: dict[str, float] = {}
    for *_, conf, cls in res_det.boxes.data.tolist():
        label = model.names[int(cls)]
        label = label.lower().replace(" ", "_").replace("-", "_").replace("/", "_")
        if conf > scores.get(label, 0):
            scores[label] = conf
    logger.debug(f"PPE scores: {scores}")
    return scores


def _log_status(redis, entry, status, conf, snap_dir) -> None:
    """Record ``status`` outcome and related events."""
    cfg = entry.get("cfg", {})
    ts = int(time.time())
    path = entry.get("path")
    img_path = Path(path) if path else Path()
    if path and not img_path.is_absolute():
        img_path = Path(snap_dir) / img_path.name
    log = {
        "ts": ts,
        "cam_id": entry.get("cam_id"),
        "track_id": entry.get("track_id"),
        "status": status,
        "conf": conf,
        "path": str(img_path.name) if path else "",
    }
    redis.zadd("ppe_logs", {json.dumps(log): ts})
    retention = int(cfg.get("ppe_log_retention_secs", 0)) or None
    trim_sorted_set_sync(redis, "ppe_logs", ts, retention)
    redis.incr("ppe_report_version")
    if status.startswith("no_"):
        redis.incr(f"{status}_count")
        event = {
            "ts": ts,
            "event": events.PPE_VIOLATION,
            "cam_id": entry.get("cam_id"),
            "track_id": entry.get("track_id"),
            "status": status,
            "path": str(img_path.name) if path else "",
        }
        redis.zadd("events", {json.dumps(event): ts})
    if cfg.get("debug_logs"):
        logger.debug(f"[{entry.get('cam_id')}] {status} conf={conf:.2f}")


# PPEDetector class encapsulates ppedetector behavior
class PPEDetector(threading.Thread):
    """Background worker that reads entries from ``ppe_queue`` and performs PPE detection."""

    # __init__ routine
    def __init__(self, cfg: dict, redis_client, snap_dir: Path, update_callback=None):
        super().__init__(daemon=True)
        self.cfg = cfg
        self.redis = redis_client
        self.device = get_device(min_gb=cfg.get("ppe_min_gb", 1.0))
        if getattr(self.device, "type", "") != "cuda":
            logger.warning("CUDA device not available, using CPU for PPE detection")

        def log_mem(note: str) -> None:
            mem = psutil.virtual_memory()
            logger.debug(f"{note}: RAM available {mem.available / (1024**3):.2f} GB")
            if getattr(self.device, "type", "") == "cuda" and torch:
                free, _ = torch.cuda.mem_get_info(self.device)
                logger.debug(f"{note}: GPU available {free / (1024**3):.2f} GB")

        log_mem("Before loading PPE model")
        try:
            from .model_registry import get_yolo

            self.model = get_yolo(cfg.get("ppe_model", "mymodel.pt"), self.device)
        except RuntimeError as e:
            raise RuntimeError(
                f"Failed to load PPE model: {e}. Disable PPE detection or use smaller weights."
            ) from e
        if getattr(self.device, "type", "") == "cuda" and torch:
            logger.info(f"\U0001f9e0 CUDA Enabled: {torch.cuda.get_device_name(0)}")

        self.last_ts = int(self.redis.get("ppe_worker:last_ts") or 0)
        self.snap_dir = Path(snap_dir)
        self.running = True
        self.update_callback = update_callback
        self._last_status_ts: dict[tuple[int, str], int] = {}

    @staticmethod
    # _clean_label routine
    def _clean_label(name: str) -> str:
        """Normalize labels to lowercase with underscores."""
        return name.lower().replace(" ", "_").replace("-", "_").replace("/", "_")

    # _should_log routine
    def _should_log(self, track_id: int, status: str, ts: int) -> bool:
        """Return True if the (track_id, status) pair is outside the cooldown."""
        cooldown = int(self.cfg.get("duplicate_bypass_seconds", 0))
        last = self._last_status_ts.get((track_id, status), 0)
        if ts - last < cooldown:
            return False
        self._last_status_ts[(track_id, status)] = ts
        return True

    # run routine
    def run(self):
        register_thread("PPEWorker")
        logger.info("PPEWorker started")
        frame_idx = 0
        last_log = time.time()
        skip = int(self.cfg.get("frame_skip", self.cfg.get("skip_frames", 0)))
        while self.running:
            entry = _fetch_job(self.redis)
            if entry:
                self.last_ts = max(self.last_ts, entry.get("ts", 0))
                self.redis.set("ppe_worker:last_ts", self.last_ts)
                if entry.get("needs_ppe") and entry.get("path"):
                    img_path = Path(entry["path"])
                    if not img_path.is_absolute():
                        img_path = self.snap_dir / img_path.name
                    img = cv2.imread(str(img_path))
                    if img is None:
                        continue
                    frame_idx += 1
                    if skip and frame_idx % skip:
                        continue
                    scores = _analyze_frame(img, self.model, self.cfg)
                    thresh = self.cfg.get("helmet_conf_thresh", 0.5)
                    entry["cfg"] = self.cfg
                    for item in self.cfg.get("track_ppe", []):
                        status, conf = determine_status(scores, item, thresh)
                        if not self._should_log(
                            entry.get("track_id"), status, int(time.time())
                        ):
                            continue
                        _log_status(self.redis, entry, status, conf, self.snap_dir)
                        if self.update_callback:
                            self.update_callback()
            if time.time() - last_log > 10:
                if frame_idx > 0:
                    elapsed = time.time() - last_log
                    logger.info(
                        f"PPEWorker processed {frame_idx} frames in {elapsed:.1f}s"
                    )
                    if self.cfg.get("enable_profiling"):
                        log_resource_usage("PPEWorker")
                    frame_idx = 0
                last_log = time.time()
        logger.info("PPEWorker stopped")
