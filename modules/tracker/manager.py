"""High level tracker manager coordinating detection, tracking and streaming."""

from __future__ import annotations

import json
import queue
import time
from collections import deque
from collections.abc import Iterable
from datetime import date
from typing import Any

import cv2
import numpy as np
import psutil
from loguru import logger
from redis.exceptions import RedisError

from core.config import ANOMALY_ITEMS
from modules.profiler import register_thread
from utils.gpu import get_device
from utils.overlay import OverlayThrottler
from utils.redis import get_sync_client, trim_sorted_set_sync
from utils.url import get_stream_type


class FaceDetector:
    """Stub detector when face recognition is disabled."""

    def detect(self, rgb):  # pragma: no cover - no-op
        return []

    def detect_boxes(self, rgb):  # pragma: no cover - no-op
        return []

from ..duplicate_filter import DuplicateFilter
from ..overlay import draw_overlays
from ..renderer import RendererProcess
from ..utils import SNAP_DIR, lock
from .detector import Detector
from .stream import CaptureWorker
from .tracker import Tracker

try:  # optional heavy dependency
    import torch  # type: ignore
except ModuleNotFoundError:  # pragma: no cover - torch is optional in tests
    torch = None

try:  # optional heavy dependency
    from deep_sort_realtime.deepsort_tracker import DeepSort  # type: ignore
except Exception:  # pragma: no cover - optional in tests
    DeepSort = None


def infer_batch(
    tracker: "PersonTracker", batch: list[np.ndarray], frames: list[np.ndarray]
) -> list[Any]:
    """Run batched detection and enqueue frame/detection pairs."""
    try:
        dets_batch = tracker.detector.detect_batch(batch, tracker.groups)
        for frm, dets in zip(frames, dets_batch):
            if tracker.det_queue.full():
                try:
                    tracker.det_queue.get_nowait()
                except queue.Empty:  # pragma: no cover - queue emptied
                    pass
            try:
                tracker.det_queue.put((frm, dets), timeout=1)
            except queue.Full:  # pragma: no cover - queue full
                pass
        return dets_batch
    except Exception:
        logger.exception(f"[{tracker.cam_id}] infer error")
        return []


def process_frame(
    tracker: "PersonTracker", frame: np.ndarray, detections: list[Any]
) -> None:
    """Process a single frame with associated detections."""
    purge = getattr(tracker, "_purge_counted", None)
    if purge:
        purge()
    if getattr(tracker, "face_tracking_enabled", False):
        tracker._process_faces(frame)
    updated = False
    rgb = None
    faces: list[tuple[int, int, int, int, np.ndarray]] = []
    if getattr(tracker, "enable_face_counting", False):
        if not getattr(tracker, "face_detector", None):
            tracker.face_detector = FaceDetector()
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        for f in tracker.face_detector.detect(rgb):
            l2, t2, r2, b2 = map(int, f.bbox)
            if f.det_score < tracker.face_count_conf:
                continue
            if (
                r2 - l2 < tracker.face_count_min_size
                or b2 - t2 < tracker.face_count_min_size
            ):
                continue
            faces.append((l2, t2, r2, b2, f.embedding))
    if getattr(tracker, "tracker", None):
        if not detections:
            now = time.time()
            interval = (
                0.0
                if not getattr(tracker, "detector_fps", 0)
                else 1.0 / float(tracker.detector_fps)
            )
            last_ts = getattr(tracker, "_last_det_ts", 0.0)
            run_det = interval == 0.0 or now - last_ts >= interval
            if run_det:
                if getattr(tracker, "detector", None):
                    detections = tracker.detector.detect(frame, tracker.groups)
                else:  # pragma: no cover - exercised in unit tests
                    from modules.tracker import detector as det

                    detections = det.profile_predict(
                        None, "person", frame, device=tracker.device
                    )
                tracker._last_det_ts = now
                tracker.last_detections = detections

        ds_tracks = tracker.tracker.update_tracks(detections, frame=frame)
        new_tracks = {}
        h, w = frame.shape[:2]
        line_pos = int(
            (h if tracker.line_orientation == "horizontal" else w) * tracker.line_ratio
        )
        for trk in ds_tracks:
            if not trk.is_confirmed():
                continue
            tid = trk.track_id
            l, t1, r, b = map(int, trk.to_ltrb())  # noqa: E741
            cx = (l + r) // 2
            cy = (t1 + b) // 2
            if tracker.line_orientation == "horizontal":
                zone = "top" if cy < line_pos else "bottom"
            else:
                zone = "left" if cx < line_pos else "right"
            prev = tracker.tracks.get(tid, {})
            prev_zone = prev.get("zone")
            group = getattr(trk, "det_class", prev.get("group", "person"))
            conf = float(getattr(trk, "det_conf", 0.0) or 0.0)
            trail = prev.get("trail", [])
            trail.append((cx, cy))
            if len(trail) > 30:
                trail = trail[-30:]
            new_tracks[tid] = {
                "bbox": (l, t1, r, b),
                "zone": zone,
                "trail": trail,
                "group": group,
                "conf": conf,
            }
            if (
                prev_zone
                and prev_zone != zone
                and {"in_count", "out_count"}
                & set(getattr(tracker, "tasks", ["in_count", "out_count"]))
            ):
                if tracker.line_orientation == "horizontal":
                    entered = prev_zone == "top" and zone == "bottom"
                else:
                    entered = prev_zone == "left" and zone == "right"
                if tracker.reverse:
                    entered = not entered
                direction = "in" if entered else "out"
                now = time.time()
                last = tracker._counted.get(tid)
                if not last or now - last[0] >= tracker.count_cooldown:
                    if entered:
                        tracker.in_counts[group] = tracker.in_counts.get(group, 0) + 1
                    else:
                        tracker.out_counts[group] = tracker.out_counts.get(group, 0) + 1
                    updated = True
                    tracker._counted[tid] = (now, direction)
                    ts = int(now)
                    path = None
                    try:
                        crop = frame[t1:b, l:r]
                        fname = f"{ts}_{tracker.cam_id}_{tid}.jpg"
                        img_path = tracker.snap_dir / fname
                        cv2.imwrite(str(img_path), crop)
                        path = str(img_path)
                    except Exception:
                        path = None
                    entry = {
                        "ts": ts,
                        "cam_id": tracker.cam_id,
                        "track_id": tid,
                        "direction": direction,
                        "label": group,
                        "path": path,
                    }
                    if getattr(tracker, "ppe_classes", []):
                        entry["needs_ppe"] = group == "person"
                    key = "person_logs" if group == "person" else "vehicle_logs"
                    tracker.redis.zadd(key, {json.dumps(entry): entry["ts"]})
                    trim_sorted_set_sync(tracker.redis, key, entry["ts"])
                    if (
                        getattr(tracker, "enable_face_counting", False)
                        and getattr(tracker, "face_counter", None)
                        and faces
                    ):
                        for fl, ft, fr, fb, emb in faces:
                            if fl >= l and ft >= t1 and fr <= r and fb <= b:
                                if tracker.face_counter.is_new(emb):
                                    if entered:
                                        tracker.in_counts["face"] = (
                                            tracker.in_counts.get("face", 0) + 1
                                        )
                                    else:
                                        tracker.out_counts["face"] = (
                                            tracker.out_counts.get("face", 0) + 1
                                        )
                                    updated = True
                                    face_entry = {
                                        "ts": ts,
                                        "cam_id": tracker.cam_id,
                                        "track_id": tid,
                                        "direction": direction,
                                        "label": "face",
                                    }
                                    tracker.redis.zadd(
                                        "face_logs",
                                        {json.dumps(face_entry): face_entry["ts"]},
                                    )
                                    trim_sorted_set_sync(
                                        tracker.redis,
                                        "face_logs",
                                        face_entry["ts"],
                                    )
                                break
        tracker.tracks = new_tracks
        if {"in_count", "out_count"} & set(
            getattr(tracker, "tasks", ["in_count", "out_count"])
        ):
            tracker.in_count = sum(tracker.in_counts.values())
            tracker.out_count = sum(tracker.out_counts.values())
        if updated and tracker.update_callback:
            try:
                tracker.update_callback()
            except Exception:
                logger.exception("update_callback failed")
    debug_flags = {
        name: getattr(tracker, name, False)
        for name in (
            "show_lines",
            "show_ids",
            "show_track_lines",
            "show_counts",
            "show_face_boxes",
        )
    }
    processed = frame.copy() if any(debug_flags.values()) else frame
    if any(debug_flags.values()):
        face_boxes = None
        if debug_flags["show_face_boxes"]:
            if not getattr(tracker, "face_detector", None):
                tracker.face_detector = FaceDetector()
            if rgb is None:
                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            face_boxes = tracker.face_detector.detect_boxes(rgb)
        if getattr(tracker, "renderer", None):
            try:
                while True:
                    tracker.renderer.queue.get_nowait()
            except queue.Empty:
                pass
            tracker.renderer.frame[:] = frame
            tracker.renderer.queue.put(
                {
                    "tracks": tracker.tracks,
                    "flags": debug_flags,
                    "line_orientation": tracker.line_orientation,
                    "line_ratio": tracker.line_ratio,
                    "in_count": tracker.in_count,
                    "out_count": tracker.out_count,
                    "face_boxes": face_boxes,
                }
            )
        else:
            draw_overlays(
                processed,
                tracker.tracks,
                debug_flags["show_ids"],
                debug_flags["show_track_lines"],
                debug_flags["show_lines"],
                tracker.line_orientation,
                tracker.line_ratio,
                debug_flags["show_counts"],
                tracker.in_count,
                tracker.out_count,
                face_boxes,
            )
        with lock:
            tracker.output_frame = processed
    else:
        with lock:
            tracker.output_frame = None
    if tracker.out_queue.full():
        try:
            tracker.out_queue.get_nowait()
        except queue.Empty:
            pass
    try:
        tracker.out_queue.put(processed, timeout=1)
    except queue.Full:
        pass


class InferWorker:
    """Background worker handling preprocessing and batched inference."""

    def __init__(self, tracker: "PersonTracker") -> None:
        self.tracker = tracker

    def run(self) -> None:
        t = self.tracker
        register_thread(f"Tracker-{t.cam_id}-infer")
        logger.info(f"[{t.cam_id}] infer loop started")
        batch: list[np.ndarray] = []
        frames: list[np.ndarray] = []
        batch_size = getattr(t, "batch_size", 1)
        while t.running or not t.frame_queue.empty() or batch:
            try:
                frame = t.frame_queue.get(timeout=1)
                frames.append(frame)
                batch.append(frame)
                if len(batch) < batch_size:
                    continue
            except queue.Empty:
                if not batch:
                    continue
            infer_batch(t, batch, frames)
            batch = []
            frames = []
        logger.info(f"[{t.cam_id}] infer loop stopped")


class PostProcessWorker:
    """Consume detections, run tracking and overlay, and publish frames."""

    def __init__(self, tracker: "PersonTracker") -> None:
        self.tracker = tracker

    def run(self) -> None:
        t = self.tracker
        register_thread(f"Tracker-{t.cam_id}-post")
        logger.info(f"[{t.cam_id}] post-process loop started")
        while t.running or not t.det_queue.empty():
            try:
                frame, detections = t.det_queue.get(timeout=1)
            except queue.Empty:
                continue
            try:
                process_frame(t, frame, detections)
            except Exception:
                logger.exception(f"[{t.cam_id}] process error")
            t.debug_stats["last_process_ts"] = time.time()
        logger.info(f"[{t.cam_id}] post-process loop stopped")
        if getattr(t, "renderer", None):
            t.renderer.close()
        if getattr(t, "face_tracking_enabled", False):
            t._finalize_face_tracks()


# ProcessingWorker class encapsulates a simplified processing loop
class ProcessingWorker:
    """Process frames by running detection (optionally throttled) and tracking."""

    def __init__(self, tracker: "PersonTracker") -> None:
        self.tracker = tracker

    def run(self) -> None:
        t = self.tracker
        while t.running or not t.frame_queue.empty():
            try:
                frame = t.frame_queue.get(timeout=1)
            except queue.Empty:
                continue
            detections = []
            now = time.time()
            interval = (
                0.0
                if not getattr(t, "detector_fps", 0)
                else 1.0 / float(t.detector_fps)
            )
            last_ts = getattr(t, "_last_det_ts", 0.0)
            run_det = interval == 0.0 or now - last_ts >= interval
            if run_det and getattr(t, "detector", None):
                detections = t.detector.detect(frame, t.groups)
                t._last_det_ts = now
            t.tracker.update_tracks(detections, frame=frame)


# UniqueFaceCounter class encapsulates uniquefacecounter behavior
class UniqueFaceCounter:
    """Filter to count unique faces using embeddings."""

    # __init__ routine
    def __init__(self, similarity: float = 0.6, max_age: int = 30) -> None:
        self.records: deque[tuple[np.ndarray, float]] = deque()
        self.similarity = similarity
        self.max_age = max_age

    # _purge routine
    def _purge(self, now: float) -> None:
        while self.records and now - self.records[0][1] > self.max_age:
            self.records.popleft()

    # is_new routine
    def is_new(self, emb: np.ndarray) -> bool:
        now = time.time()
        self._purge(now)
        for e, _ in self.records:
            sim = float(np.dot(e, emb) / (np.linalg.norm(e) * np.linalg.norm(emb)))
            if sim >= self.similarity:
                return False
        self.records.append((emb, now))
        return True


# _iou routine
def _iou(a: tuple[int, int, int, int], b: tuple[int, int, int, int]) -> float:
    """Return intersection-over-union for two boxes."""
    ax1, ay1, ax2, ay2 = a
    bx1, by1, bx2, by2 = b
    inter_x1 = max(ax1, bx1)
    inter_y1 = max(ay1, by1)
    inter_x2 = min(ax2, bx2)
    inter_y2 = min(ay2, by2)
    iw = max(0, inter_x2 - inter_x1)
    ih = max(0, inter_y2 - inter_y1)
    inter = iw * ih
    if inter == 0:
        return 0.0
    area_a = (ax2 - ax1) * (ay2 - ay1)
    area_b = (bx2 - bx1) * (by2 - by1)
    return inter / float(area_a + area_b - inter)


# LightweightFaceTracker class encapsulates a minimal IoU tracker
class LightweightFaceTracker:
    """Very small tracker assigning IDs using IoU matching."""

    def __init__(self, iou_thresh: float = 0.5) -> None:
        self.next_id = 0
        self.tracks: dict[int, tuple[int, int, int, int]] = {}
        self.iou_thresh = iou_thresh

    # update routine
    def update(
        self, detections: list[tuple[int, int, int, int, float]]
    ) -> list[tuple[int, tuple[int, int, int, int], float]]:
        """Update tracker with ``detections`` and return active tracks."""
        assigned: dict[int, bool] = {}
        results: list[tuple[int, tuple[int, int, int, int], float]] = []
        for x1, y1, x2, y2, conf in detections:
            best_id = None
            best_iou = 0.0
            for tid, bbox in self.tracks.items():
                iou = _iou(bbox, (x1, y1, x2, y2))
                if iou > best_iou and iou >= self.iou_thresh:
                    best_iou = iou
                    best_id = tid
            if best_id is None:
                best_id = self.next_id
                self.next_id += 1
            self.tracks[best_id] = (x1, y1, x2, y2)
            results.append((best_id, (x1, y1, x2, y2), conf))
            assigned[best_id] = True
        self.tracks = {
            tid: bbox for tid, bbox in self.tracks.items() if tid in assigned
        }
        return results


# PersonTracker class encapsulates persontracker behavior
class PersonTracker:
    """Tracks entry and exit counts using YOLOv8 and DeepSORT."""

    # __init__ routine
    def __init__(
        self,
        cam_id: int,
        src: str,
        classes: list[str],
        cfg: dict,
        tasks: list[str] | None = None,
        src_type: str | None = None,
        line_orientation: str | None = None,
        reverse: bool = False,
        resolution: str = "original",
        rtsp_transport: str = "tcp",
        update_callback=None,
    ):
        self.cfg = cfg
        for k, v in cfg.items():
            setattr(self, k, v)
        self.load_durations: dict[str, float] = {}
        self.pipeline = cfg.get("pipeline", "")
        self.enable_face_counting = cfg.get("enable_face_counting", False)
        self.face_count_conf = cfg.get("face_count_conf", 0.85)
        self.face_count_similarity = cfg.get("face_count_similarity", 0.6)
        self.face_count_min_size = cfg.get("face_count_min_size", 80)
        self.face_detector = None
        self.face_counter = (
            UniqueFaceCounter(self.face_count_similarity)
            if self.enable_face_counting
            else None
        )
        self.cam_id = cam_id
        self.src = src
        self.src_type = src_type or cfg.get("type") or get_stream_type(src)
        self.classes = classes
        self.tasks = tasks or ["in_count", "out_count"]
        self.count_classes = cfg.get("count_classes", [])
        self.ppe_classes = cfg.get("ppe_classes", [])
        self.alert_anomalies = cfg.get("alert_anomalies", [])
        self.line_orientation = line_orientation or cfg.get(
            "line_orientation", "vertical"
        )
        self.reverse = reverse
        self.resolution = resolution
        self.rtsp_transport = rtsp_transport
        self.stream_mode = cfg.get("stream_mode", "gstreamer")
        self.helmet_conf_thresh = cfg.get("helmet_conf_thresh", 0.5)
        self.detect_helmet_color = cfg.get("detect_helmet_color", False)
        self.track_misc = cfg.get("track_misc", True)
        self.show_lines = cfg.get("show_lines", True)
        self.show_ids = cfg.get("show_ids", True)
        self.show_track_lines = cfg.get("show_track_lines", False)
        self.show_counts = cfg.get("show_counts", False)
        self.show_face_boxes = cfg.get("show_face_boxes", False)
        self.preview_scale = cfg.get("preview_scale", 1.0)
        self.detector_fps = cfg.get("detector_fps", 10)
        self.adaptive_skip = cfg.get("adaptive_skip", False)

        self.debug_logs = cfg.get("debug_logs", False)
        self.ffmpeg_high_watermark = cfg.get("ffmpeg_high_watermark", 0)
        self.ffmpeg_low_watermark = cfg.get("ffmpeg_low_watermark", 0)
        self.duplicate_filter_enabled = cfg.get("duplicate_filter_enabled", False)
        self.duplicate_filter_threshold = cfg.get("duplicate_filter_threshold", 0.1)
        self.duplicate_bypass_seconds = cfg.get("duplicate_bypass_seconds", 2)
        if self.ffmpeg_high_watermark:
            self.duplicate_filter_enabled = False
        self.max_retry = cfg.get("max_retry", 5)
        self.update_callback = update_callback
        self.online = False
        self.restart_capture = False

        if any(
            [
                self.show_lines,
                self.show_ids,
                self.show_track_lines,
                self.show_counts,
                self.show_face_boxes,
            ]
        ):
            try:
                w, h = map(int, str(resolution).split("x"))
            except Exception:
                w, h = 640, 480
            shape = (h, w, 3)
            self.renderer = RendererProcess(shape)
            self.output_frame = self.renderer.output
        else:
            self.renderer = None
            self.output_frame = None

        self.dup_filter = (
            DuplicateFilter(
                self.duplicate_filter_threshold, self.duplicate_bypass_seconds
            )
            if self.duplicate_filter_enabled
            else None
        )
        # Resolve device; "auto" prefers GPU and falls back to CPU with warning.
        self.device = get_device(device=cfg.get("device"))
        logger.info(f"Loading person model {self.person_model} on {self.device.type}")
        if self.device.type == "cuda":
            logger.info(f"\U0001f9e0 CUDA Enabled: {torch.cuda.get_device_name(0)}")

        def log_mem(note: str) -> None:
            mem = psutil.virtual_memory()
            logger.debug(f"{note}: RAM available {mem.available / (1024**3):.2f} GB")
            if getattr(self.device, "type", "") == "cuda" and torch:
                free, _ = torch.cuda.mem_get_info(self.device)
                logger.debug(f"{note}: GPU available {free / (1024**3):.2f} GB")

        log_mem("Before loading person model")
        try:
            from ..model_registry import get_yolo

            start = time.perf_counter()
            self.model_person = get_yolo(self.person_model, self.device)
            self.load_durations["person_model"] = time.perf_counter() - start
            logger.info(
                "Person model loaded in {:.2f}s",
                self.load_durations["person_model"],
            )
        except RuntimeError as e:
            raise RuntimeError(
                f"Failed to load person model: {e}. Disable this feature or use smaller weights.",
            ) from e
        self.detector = Detector(self.model_person, self.device)
        self.batch_size = max(2, min(int(cfg.get("batch_size", 2)), 4))
        qsize = cfg.get("queue_size", 10)
        self.frame_queue = queue.Queue(maxsize=qsize)
        self.det_queue = queue.Queue(maxsize=qsize)
        self.out_queue = queue.Queue(maxsize=qsize)
        log_mem("Before loading plate model")
        try:
            plate_path = cfg.get("plate_model") or "license_plate_detector.pt"
            logger.info(f"Plate model: {plate_path}")
            start = time.perf_counter()
            self.model_plate = get_yolo(plate_path, self.device)
            self.load_durations["plate_model"] = time.perf_counter() - start
            logger.info(
                "Plate model loaded in {:.2f}s",
                self.load_durations["plate_model"],
            )
        except RuntimeError as e:
            raise RuntimeError(
                f"Failed to load plate model: {e}. Disable this feature or use smaller weights.",
            ) from e
        self.email_cfg = cfg.get("email", {})
        if getattr(self.device, "type", "") == "cuda" and torch:
            torch.backends.cudnn.benchmark = True
        self.use_gpu_embedder = getattr(self.device, "type", "") == "cuda"
        log_mem("Before initializing DeepSort")
        try:
            start = time.perf_counter()
            self.tracker = Tracker(self.use_gpu_embedder)
            self.load_durations["tracker"] = time.perf_counter() - start
            logger.info(
                "DeepSort initialized in {:.2f}s",
                self.load_durations["tracker"],
            )
        except RuntimeError as e:
            raise RuntimeError(
                f"Failed to initialize DeepSort: {e}. Disable this feature or use smaller weights.",
            ) from e
        self.unique_counter = UniqueFaceCounter(similarity=self.face_count_similarity)
        features = cfg.get("features", {})
        self.face_tracking_enabled = bool(
            features.get("in_out_counting") and features.get("face_recognition")
        )
        self.face_tracker = None
        self.face_detector = None
        self.face_best: dict[int, tuple[float, str]] = {}
        self.face_active_ids: set[int] = set()
        if self.face_tracking_enabled:
            try:
                self.face_detector = FaceDetector()
            except Exception:
                self.face_detector = None
            if self.face_detector:
                if DeepSort is not None:
                    try:
                        self.face_tracker = DeepSort(max_age=5, embedder_gpu=False)
                    except Exception:
                        self.face_tracker = LightweightFaceTracker()
                else:
                    self.face_tracker = LightweightFaceTracker()
        self.tracks = {}
        self._counted: dict[int, tuple[float, str]] = {}
        self.count_cooldown = cfg.get("count_cooldown", 2)
        try:
            self.redis = get_sync_client(self.redis_url)
        except (RedisError, OSError) as e:
            logger.error(f"[{self.cam_id}] Redis connection failed: {e}")
            raise

        key_prefix = f"person_tracker:cam:{self.cam_id}"
        self.key_in = f"{key_prefix}:in"
        self.key_out = f"{key_prefix}:out"
        self.key_date = f"{key_prefix}:date"
        # ``track_objects`` accepts raw labels or alias names defined in
        # ``GROUP_ALIASES``.
        groups = cfg.get("track_objects", ["person"])
        if isinstance(groups, str) or not isinstance(groups, Iterable):
            groups = [groups]
        else:
            groups = list(groups)
        self.groups = groups
        self.in_counts = {}
        self.out_counts = {}
        keys_in = [f"{self.key_in}:{g}" for g in self.groups]
        keys_out = [f"{self.key_out}:{g}" for g in self.groups]
        vals = self.redis.mget(keys_in + keys_out)
        split = len(self.groups)
        for idx, g in enumerate(self.groups):
            self.in_counts[g] = int(vals[idx] or 0)
            self.out_counts[g] = int(vals[idx + split] or 0)
        self.in_count = sum(self.in_counts.values())
        self.out_count = sum(self.out_counts.values())
        stored_date = self.redis.get(self.key_date)
        self.prev_date = (
            date.fromisoformat(stored_date) if stored_date else date.today()
        )
        init_data = {self.key_date: self.prev_date.isoformat()}
        for g in self.groups:
            init_data[f"{self.key_in}:{g}"] = self.in_counts[g]
            init_data[f"{self.key_out}:{g}"] = self.out_counts[g]
        self.redis.mset(init_data)
        today = date.today().isoformat()
        date_keys = [f"{item}_date" for item in ANOMALY_ITEMS]
        date_vals = self.redis.mget(date_keys)
        anomaly_init: dict[str, Any] = {}
        for item, d_raw in zip(ANOMALY_ITEMS, date_vals):
            d = date.fromisoformat(d_raw) if d_raw else self.prev_date
            if d.isoformat() != today:
                anomaly_init[f"{item}_count"] = 0
                anomaly_init[f"{item}_date"] = today
        if anomaly_init:
            self.redis.mset(anomaly_init)
        self.snap_dir = SNAP_DIR
        self.raw_frame = None
        self.output_frame = None
        # Parameters for the downscaled/throttled preview stream
        self.preview_downscale = cfg.get("preview_downscale", 2)
        self._last_preview_ts = 0.0
        self.viewers = 0
        self.running = True
        self.capture_backend = None
        self.pipeline_info = ""
        self.stream_status = ""
        self.stream_error = ""
        self.log_interval = cfg.get("log_interval", 30)
        self._log_count = 0
        # Stats for debugging
        self.debug_stats = {
            "capture_fps": 0.0,
            "process_fps": 0.0,
            "queue": 0,
            "last_capture_ts": None,
            "last_process_ts": None,
        }
        # Timestamp of the last debug restart
        self.debug_restart_ts: float | None = None

        # Workers
        self.capture_worker = CaptureWorker(self)
        self.infer_worker = InferWorker(self)
        self.post_worker = PostProcessWorker(self)

    @staticmethod
    # _clean_label routine
    def _clean_label(name: str) -> str:
        """Normalize a label to lowercase with underscores."""
        return name.lower().replace(" ", "_").replace("-", "_").replace("/", "_")

    # _log_process_interval routine
    def _log_process_interval(self, delta: float) -> None:
        """Log processing interval every N frames to avoid log spam."""
        self._log_count += 1
        if self._log_count % self.log_interval == 0:
            logger.debug(f"[{self.cam_id}] process interval={delta:.3f}s")

    def _purge_counted(self, now: float | None = None) -> None:
        if not hasattr(self, "_counted"):
            self._counted = {}
        if not hasattr(self, "count_cooldown"):
            self.count_cooldown = 2
        now = now or time.time()
        cutoff = now - self.count_cooldown
        self._counted = {tid: v for tid, v in self._counted.items() if v[0] >= cutoff}

    # _process_faces routine
    def _process_faces(self, frame: np.ndarray) -> None:
        if not (self.face_tracker and self.face_detector):
            return
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        faces = self.face_detector.detect(rgb)
        detections = []
        for f in faces:
            x1, y1, x2, y2 = [int(v) for v in f.bbox]
            conf = float(getattr(f, "det_score", 0.0))
            detections.append((x1, y1, x2, y2, conf))
        prev_ids = set(self.face_active_ids)
        self.face_active_ids = set()
        if isinstance(self.face_tracker, LightweightFaceTracker):
            tracks = self.face_tracker.update(detections)
        else:
            ds_dets = [
                ([x1, y1, x2 - x1, y2 - y1], conf, "face")
                for x1, y1, x2, y2, conf in detections
            ]
            ds_tracks = self.face_tracker.update_tracks(ds_dets, frame=frame)
            tracks = []
            for trk in ds_tracks:
                if not trk.is_confirmed():
                    continue
                l, t1, r, b = map(int, trk.to_ltrb())  # noqa: E741
                conf = float(getattr(trk, "det_conf", 0.0) or 0.0)
                tracks.append((trk.track_id, (l, t1, r, b), conf))
        for tid, bbox, conf in tracks:
            self.face_active_ids.add(tid)
            best = self.face_best.get(tid)
            if not best or conf > best[0]:
                x1, y1, x2, y2 = bbox
                crop = frame[y1:y2, x1:x2]
                fname = f"{int(time.time())}_{self.cam_id}_{tid}.jpg"
                path = self.snap_dir / fname
                try:
                    cv2.imwrite(str(path), crop)
                    self.face_best[tid] = (conf, str(path))
                except Exception:
                    continue
        ended_ids = prev_ids - self.face_active_ids
        for tid in list(ended_ids):
            self._log_face_snapshot(tid)

    # _log_face_snapshot routine
    def _log_face_snapshot(self, tid: int) -> None:
        data = self.face_best.pop(tid, None)
        if not data:
            return
        conf, path = data
        ts = int(time.time())
        entry = {"ts": ts, "cam_id": self.cam_id, "track_id": tid, "path": path}
        self.redis.zadd("face_logs", {json.dumps(entry): ts})
        trim_sorted_set_sync(self.redis, "face_logs", ts)

    # _finalize_face_tracks routine
    def _finalize_face_tracks(self) -> None:
        for tid in list(self.face_best.keys()):
            self._log_face_snapshot(tid)
        self.face_active_ids.clear()

    # update_cfg routine
    def update_cfg(self, cfg: dict):
        if "device" in cfg and torch is not None:
            # Normalize device configuration; "auto" selects GPU when available.
            cfg["device"] = get_device(device=cfg["device"])

        for k, v in cfg.items():
            setattr(self, k, v)
        # update object classes if provided
        if "object_classes" in cfg:
            self.classes = cfg["object_classes"]
        if "count_classes" in cfg:
            self.count_classes = cfg["count_classes"]
        if "ppe_classes" in cfg:
            self.ppe_classes = cfg["ppe_classes"]
        if "tasks" in cfg:
            self.tasks = cfg["tasks"]
            if not isinstance(self.tasks, list):
                self.tasks = ["in_count", "out_count"]
        if "type" in cfg:
            self.src_type = cfg["type"]
        if "alert_anomalies" in cfg:
            self.alert_anomalies = cfg["alert_anomalies"]
        if "line_orientation" in cfg:
            self.line_orientation = cfg["line_orientation"]
        if "reverse" in cfg:
            self.reverse = bool(cfg["reverse"])
        if "resolution" in cfg:
            self.resolution = cfg["resolution"]
        if "stream_mode" in cfg:
            self.stream_mode = cfg["stream_mode"]
        if "helmet_conf_thresh" in cfg:
            self.helmet_conf_thresh = cfg["helmet_conf_thresh"]
        if "detect_helmet_color" in cfg:
            self.detect_helmet_color = cfg["detect_helmet_color"]
        if "track_misc" in cfg:
            self.track_misc = cfg["track_misc"]
        if "show_lines" in cfg:
            self.show_lines = cfg["show_lines"]
        if "show_ids" in cfg:
            self.show_ids = cfg["show_ids"]
        if "show_track_lines" in cfg:
            self.show_track_lines = cfg["show_track_lines"]
        if "show_counts" in cfg:
            self.show_counts = cfg["show_counts"]
        if "show_face_boxes" in cfg:
            self.show_face_boxes = cfg["show_face_boxes"]
        if "detector_fps" in cfg:
            self.detector_fps = cfg["detector_fps"]
        if "adaptive_skip" in cfg:
            self.adaptive_skip = cfg["adaptive_skip"]
        if "overlay_every_n" in cfg:
            self.overlay_every_n = cfg["overlay_every_n"]
        if "overlay_min_ms" in cfg:
            self.overlay_min_ms = cfg["overlay_min_ms"]
        if "overlay_every_n" in cfg or "overlay_min_ms" in cfg:
            self.overlay_throttler = OverlayThrottler(
                self.overlay_every_n, self.overlay_min_ms
            )
        if "debug_logs" in cfg:
            self.debug_logs = cfg["debug_logs"]
        if "ffmpeg_high_watermark" in cfg:
            self.ffmpeg_high_watermark = cfg["ffmpeg_high_watermark"]
            if self.ffmpeg_high_watermark:
                self.duplicate_filter_enabled = False
                self.dup_filter = None
        if "ffmpeg_low_watermark" in cfg:
            self.ffmpeg_low_watermark = cfg["ffmpeg_low_watermark"]
        if "duplicate_filter_enabled" in cfg:
            self.duplicate_filter_enabled = (
                cfg["duplicate_filter_enabled"] and not self.ffmpeg_high_watermark
            )
            self.dup_filter = (
                DuplicateFilter(
                    self.duplicate_filter_threshold, self.duplicate_bypass_seconds
                )
                if self.duplicate_filter_enabled
                else None
            )
        if "duplicate_filter_threshold" in cfg:
            self.duplicate_filter_threshold = cfg["duplicate_filter_threshold"]
            if self.dup_filter:
                self.dup_filter.threshold = self.duplicate_filter_threshold
        if "duplicate_bypass_seconds" in cfg:
            self.duplicate_bypass_seconds = cfg["duplicate_bypass_seconds"]
            if self.dup_filter:
                self.dup_filter.bypass_seconds = self.duplicate_bypass_seconds
        if "enable_face_counting" in cfg:
            self.enable_face_counting = cfg["enable_face_counting"]
        if "face_count_conf" in cfg:
            self.face_count_conf = cfg["face_count_conf"]
        if "face_count_min_size" in cfg:
            self.face_count_min_size = cfg["face_count_min_size"]
        if "face_count_similarity" in cfg and self.unique_counter:
            self.unique_counter.similarity = cfg["face_count_similarity"]
        from ..model_registry import get_yolo

        if "person_model" in cfg and cfg["person_model"] != getattr(
            self, "person_model", None
        ):
            self.person_model = cfg["person_model"]
            self.model_person = get_yolo(self.person_model, self.device)
        if "plate_model" in cfg and cfg["plate_model"] != getattr(
            self, "plate_model", None
        ):
            self.plate_model = cfg["plate_model"]
            self.model_plate = get_yolo(self.plate_model, self.device)
        if "email" in cfg:
            self.email_cfg = cfg["email"]
        if "rtsp_transport" in cfg:
            self.rtsp_transport = cfg["rtsp_transport"]

        if "track_objects" in cfg:
            new_groups = cfg["track_objects"]
            missing = [g for g in new_groups if g not in self.in_counts]
            if missing:
                m_keys_in = [f"{self.key_in}:{g}" for g in missing]
                m_keys_out = [f"{self.key_out}:{g}" for g in missing]
                vals = self.redis.mget(m_keys_in + m_keys_out)
                split = len(missing)
                for idx, g in enumerate(missing):
                    self.in_counts[g] = int(vals[idx] or 0)
                    self.out_counts[g] = int(vals[idx + split] or 0)
            for g in list(self.in_counts.keys()):
                if g not in new_groups:
                    self.in_counts.pop(g, None)
                    self.out_counts.pop(g, None)
                    self.redis.delete(f"{self.key_in}:{g}", f"{self.key_out}:{g}")
            self.groups = new_groups
            self.in_count = sum(self.in_counts.values())
            self.out_count = sum(self.out_counts.values())

    # apply_debug_pipeline routine
    def apply_debug_pipeline(self, pipeline: str | None = None, **params: dict) -> None:
        """Merge debug parameters into current config and restart capture."""
        changed = False
        if pipeline is not None and pipeline != self.cfg.get("pipeline"):
            self.cfg["pipeline"] = pipeline
            self.pipeline_info = pipeline
            self.pipeline = pipeline
            changed = True
        for k, v in params.items():
            if k == "url":
                if v != self.src:
                    self.src = v
                    changed = True
            elif k == "type":
                if v != self.src_type:
                    self.src_type = v
                    changed = True
            elif k == "resolution":
                if v != self.resolution:
                    self.resolution = v
                    changed = True
            elif k in {
                "rtsp_transport",
                "stream_mode",
                "ffmpeg_flags",
                "backend_priority",
            }:
                cur = getattr(self, k, self.cfg.get(k))
                if cur != v:
                    setattr(self, k, v)
                    self.cfg[k] = v
                    changed = True
            elif k == "pipeline":
                if v != self.cfg.get("pipeline"):
                    self.cfg["pipeline"] = v
                    self.pipeline_info = v
                    self.pipeline = v
                    changed = True
            else:
                if self.cfg.get(k) != v:
                    self.cfg[k] = v
                    changed = True
        if changed:
            self.restart_capture = True
            self.debug_restart_ts = time.time()

    # get_debug_stats routine
    def get_debug_stats(self) -> dict:
        """Return copy of current debug statistics."""
        return dict(self.debug_stats)

    # _append_runtime_debug routine
    def _append_runtime_debug(self, message: str) -> None:
        """Append runtime capture errors to Redis for diagnostics."""
        if not self.redis:
            return
        key = f"camera_debug:{self.cam_id}"
        try:
            raw = self.redis.get(key)
            data = json.loads(raw) if raw else {}
            runtime = data.setdefault("runtime", [])
            runtime.append(
                {
                    "ts": int(time.time()),
                    "backend": getattr(self, "capture_backend", ""),
                    "message": message,
                }
            )
            # keep only last 50 entries
            if len(runtime) > 50:
                data["runtime"] = runtime[-50:]
            self.redis.set(key, json.dumps(data))
        except Exception:
            pass

    # capture_loop routine
    def capture_loop(self):
        """Delegate to the capture worker."""
        self.capture_worker.run()

    # infer_loop routine
    def infer_loop(self):
        """Delegate to the inference worker."""
        self.infer_worker.run()

    # post_process_loop routine
    def post_process_loop(self):
        """Delegate to the post-process worker."""
        self.post_worker.run()
