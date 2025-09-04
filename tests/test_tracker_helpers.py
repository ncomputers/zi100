import queue
from types import SimpleNamespace

import numpy as np

import modules.tracker.manager as manager


def test_infer_batch(monkeypatch):
    calls: list[tuple[list[np.ndarray], tuple[str, ...]]] = []

    def detect_batch(batch, groups):
        calls.append((batch, tuple(groups)))
        return [["d1"], ["d2"]]

    tracker = SimpleNamespace(
        detector=SimpleNamespace(detect_batch=detect_batch),
        groups=["person"],
        det_queue=queue.Queue(maxsize=2),
        cam_id="1",
    )

    frames = [np.zeros((1, 1, 3)), np.ones((1, 1, 3))]
    res = manager.infer_batch(tracker, frames, frames)
    assert res == [["d1"], ["d2"]]
    assert calls and calls[0][0] == frames
    assert tracker.det_queue.qsize() == 2
    assert tracker.det_queue.get() == (frames[0], ["d1"])


def test_process_frame(monkeypatch):
    frame = np.zeros((2, 2, 3), dtype=np.uint8)
    detections = ["d"]
    q = queue.Queue()
    update_calls: list[tuple[list[str], np.ndarray]] = []

    def update_tracks(dets, frame=None):
        update_calls.append((dets, frame))
        return []

    tracker = SimpleNamespace(
        _purge_counted=lambda: None,
        face_tracking_enabled=False,
        enable_face_counting=False,
        tracker=SimpleNamespace(update_tracks=update_tracks),
        line_orientation="horizontal",
        line_ratio=0.5,
        tasks=["in_count", "out_count"],
        tracks={},
        in_counts={},
        out_counts={},
        in_count=0,
        out_count=0,
        update_callback=None,
        show_lines=False,
        show_ids=False,
        show_track_lines=False,
        show_counts=False,
        show_face_boxes=False,
        renderer=None,
        out_queue=q,
        output_frame=None,
        cam_id="c1",
        reverse=False,
        count_cooldown=0,
    )

    manager.process_frame(tracker, frame, detections)
    assert update_calls == [(detections, frame)]
    assert tracker.output_frame is None
    assert q.qsize() == 1
