"""Streaming helpers for the tracker package."""

from __future__ import annotations

import queue
import time
from typing import TYPE_CHECKING

import cv2

try:  # optional heavy dependency
    import torch  # type: ignore
except ModuleNotFoundError:  # pragma: no cover - torch is optional in tests
    torch = None
from loguru import logger

from modules.camera_factory import StreamUnavailable, open_capture
from modules.profiler import register_thread

if TYPE_CHECKING:
    from .manager import PersonTracker


class CaptureWorker:
    """Background worker that reads frames and feeds a queue."""

    def __init__(self, tracker: PersonTracker) -> None:
        self.tracker = tracker

    def run(self) -> None:
        t = self.tracker
        register_thread(f"Tracker-{t.cam_id}-capture")
        logger.info(f"[{t.cam_id}] capture loop started")
        cap = None
        base_skip = int(t.cfg.get("frame_skip", 0))
        skip = max(1, base_skip)
        frame_idx = 0
        prev_gray = None
        while t.running:
            try:
                dev = getattr(t, "device", None)
                if isinstance(dev, str):
                    use_gpu = dev.startswith("cuda")
                else:
                    use_gpu = getattr(dev, "type", "") == "cuda"

                cap, t.rtsp_transport = open_capture(
                    t.src,
                    t.cam_id,
                    t.src_type,
                    t.resolution,
                    t.rtsp_transport,
                    t.stream_mode,
                    use_gpu,
                    capture_buffer=t.cfg.get("capture_buffer", 3),
                    local_buffer_size=t.cfg.get("local_buffer_size", 1),
                    backend_priority=t.cfg.get("backend_priority"),
                    ffmpeg_flags=t.cfg.get("ffmpeg_flags"),
                    pipeline=t.cfg.get("pipeline"),
                    profile=t.cfg.get("profile"),
                    ffmpeg_reconnect_delay=t.cfg.get("ffmpeg_reconnect_delay"),
                    ready_frames=t.cfg.get("ready_frames"),
                    ready_duration=t.cfg.get("ready_duration"),
                    ready_timeout=t.cfg.get("ready_timeout"),
                    for_display=t.viewers > 0,
                    reverse=t.cfg.get("reverse", False),
                    orientation=t.cfg.get("orientation", "vertical"),
                )
                cmd = getattr(cap, "pipeline", None) or getattr(cap, "cmd", None)
                if isinstance(cmd, list):
                    cmd = " ".join(cmd)
                t.pipeline_info = cmd or ""
                t.capture_backend = cap.__class__.__name__
                t.stream_status = "ok"
                t.stream_error = ""
                logger.info(
                    f"[{t.cam_id}] capture backend {t.capture_backend} cmd={t.pipeline_info}"
                )
                fail_count = 0
                max_failures = t.cfg.get("max_read_failures", 30)
                while t.running:
                    if t.restart_capture:
                        t.restart_capture = False
                        fail_count = 0
                        break
                    ret, frame = cap.read()
                    if not ret or frame is None:
                        fail_count += 1
                        status = getattr(cap, "last_status", "")
                        err = getattr(cap, "last_error", "")
                        logger.warning(
                            f"[{t.cam_id}] frame read failed (status={status} error={err}) count={fail_count}"
                        )
                        if status and status != "ok":
                            logger.error(
                                f"[{t.cam_id}] restarting capture due to status {status}"
                            )
                            t.stream_status = status
                            t.stream_error = err
                            break
                        if fail_count > max_failures:
                            logger.warning(
                                f"[{t.cam_id}] too many read failures; restarting capture"
                            )
                            break
                        time.sleep(0.1)
                        continue
                    fail_count = 0
                    frame_idx += 1
                    if getattr(t, "adaptive_skip", False):
                        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                        if prev_gray is not None:
                            diff = cv2.absdiff(gray, prev_gray)
                            motion = float(diff.mean())
                            if motion < 2.0:
                                skip = min(skip + 1, 10)
                            else:
                                skip = max(1, skip - 1)
                        prev_gray = gray
                    if skip > 1 and (frame_idx - 1) % skip:
                        continue
                    if t.frame_queue.full():
                        try:
                            t.frame_queue.get_nowait()
                        except queue.Empty:
                            pass
                    t.raw_frame = frame
                    if (
                        use_gpu
                        and torch is not None
                        and not torch.cuda.is_available()
                        and not getattr(t, "_warned_no_cuda", False)
                    ):
                        logger.warning(
                            f"[{t.cam_id}] CUDA unavailable; falling back to CPU"
                        )
                        t._warned_no_cuda = True
                    try:
                        t.frame_queue.put(frame, timeout=1)
                    except queue.Full:
                        pass
                    t.debug_stats["last_capture_ts"] = time.time()
                    t.debug_stats["packet_loss"] = getattr(
                        cap, "network_error_count", 0
                    )
                    if t.cfg.get("once"):
                        t.running = False
                        break
                cap.release()
            except StreamUnavailable as e:
                logger.error(f"[{t.cam_id}] Stream unavailable: {e}")
                t.stream_status = "timeout" if "timeout" in str(e).lower() else "error"
                t.stream_error = str(e)
                t.running = False
            except Exception as e:
                status = getattr(cap, "last_status", "") if cap else ""
                err = getattr(cap, "last_error", "") if cap else ""
                cmd = getattr(cap, "pipeline", None) or getattr(cap, "cmd", None)
                if isinstance(cmd, list):
                    cmd = " ".join(cmd)
                logger.error(
                    f"[{t.cam_id}] capture error: {e}. status={status} error={err} cmd={cmd}"
                )
                t.stream_status = status or "error"
                t.stream_error = err or str(e)
                t.running = False
                if cap:
                    cap.release()
        logger.info(
            f"[{t.cam_id}] capture loop stopped. status={getattr(cap, 'last_status', '')} "
            f"error={getattr(cap, 'last_error', '')} cmd={t.pipeline_info}"
        )


__all__ = ["CaptureWorker"]
