"""Utilities for profiling threads and inference performance."""

import threading
import time
from dataclasses import dataclass, field
from typing import Dict, Optional

import psutil
from loguru import logger


@dataclass
class ProfilerState:
    """Holds profiling state for threads and inference timings."""

    thread_tags: Dict[int, str] = field(default_factory=dict)
    last_cpu_times: Dict[int, tuple[float, float]] = field(default_factory=dict)
    last_inference: Dict[str, float] = field(default_factory=dict)


default_state = ProfilerState()

_process = psutil.Process()


# register_thread routine
def register_thread(tag: str, state: ProfilerState = default_state) -> None:
    """Register current thread with a tag for profiling."""
    state.thread_tags[threading.get_native_id()] = tag


# log_inference routine
def log_inference(
    tag: str, duration: float, state: ProfilerState = default_state
) -> None:
    """Record a YOLOv8 inference duration for the given tag."""
    state.last_inference[tag] = duration


# profile_predict routine
def profile_predict(model, tag: str, *args, **kwargs):
    """Wrap YOLOv8 ``predict`` and log inference duration."""
    start = time.time()
    res = model.predict(*args, **kwargs)
    log_inference(tag, time.time() - start)
    return res


# _calc_cpu_percent routine
def _calc_cpu_percent(
    state: ProfilerState, tid: int, cpu_time: float, now: float
) -> float:
    last = state.last_cpu_times.get(tid)
    if not last:
        state.last_cpu_times[tid] = (cpu_time, now)
        return 0.0
    diff = cpu_time - last[0]
    interval = now - last[1]
    state.last_cpu_times[tid] = (cpu_time, now)
    if interval <= 0:
        return 0.0
    return (diff / interval) * 100.0 / psutil.cpu_count()


# _collect_stats routine
def _collect_stats(
    state: ProfilerState = default_state,
) -> Dict[str, tuple[float, float, Optional[float]]]:
    """Return stats for registered threads."""
    mem = _process.memory_info().rss / (1024 * 1024)
    now = time.time()
    stats = {}
    for th in _process.threads():
        tid = th.id
        tag = state.thread_tags.get(tid)
        if not tag:
            continue
        cpu_time = th.user_time + th.system_time
        cpu_pct = _calc_cpu_percent(state, tid, cpu_time, now)
        inf = state.last_inference.get(tag)
        stats[tag] = (cpu_pct, mem, inf)
    return stats


# log_resource_usage routine
def log_resource_usage(tag: str) -> None:
    """Immediately log resource usage for the given tag."""
    stats = _collect_stats().get(tag)
    if not stats:
        logger.debug(f"[Profiler] {tag} not registered")
        return
    cpu, mem, inf = stats
    msg = f"[Profiler] {tag} CPU: {cpu:.1f}%, RAM: {mem:.0f}MB"
    if inf is not None:
        msg += f", Last YOLOv8 Inference: {inf:.2f}s"
    logger.debug(msg)


# Profiler class encapsulates profiler behavior
class Profiler(threading.Thread):
    """Background profiler thread."""

    # __init__ routine
    def __init__(self, interval: int = 5):
        super().__init__(daemon=True)
        self.interval = interval
        self.running = True

    # run routine
    def run(self) -> None:
        while self.running:
            stats = _collect_stats()
            for tag, (cpu, mem, inf) in stats.items():
                msg = f"[Profiler] {tag} CPU: {cpu:.1f}%, RAM: {mem:.0f}MB"
                if inf is not None:
                    msg += f", Last YOLOv8 Inference: {inf:.2f}s"
                logger.debug(msg)
            time.sleep(self.interval)


_profiler: Optional[Profiler] = None


# start_profiler routine
def start_profiler(cfg: dict) -> None:
    """Start the background profiler if enabled in config."""
    global _profiler
    if not cfg.get("enable_profiling"):
        stop_profiler()
        return
    interval = int(cfg.get("profiling_interval", 5))
    if _profiler and _profiler.is_alive():
        _profiler.interval = interval
        return
    stop_profiler()
    _profiler = Profiler(interval)
    _profiler.start()
    logger.info(f"Profiler started with interval={interval}s")


# stop_profiler routine
def stop_profiler() -> None:
    """Stop the background profiler."""
    global _profiler
    if _profiler:
        _profiler.running = False
        _profiler.join(timeout=1)
        _profiler = None
        logger.info("Profiler stopped")
