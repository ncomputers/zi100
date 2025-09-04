import importlib
import sys

sys.modules.pop("cv2", None)
sys.modules.pop("cv2.typing", None)
sys.modules.pop("cv2.mat_wrapper", None)
import cv2  # type: ignore
import numpy as np

import modules.overlay as overlay

importlib.reload(overlay)
from modules.overlay import (
    _draw_counting_line,
    _draw_counts,
    _draw_track,
    draw_overlays,
)


def test_draw_overlays():
    frame = np.zeros((100, 100, 3), dtype=np.uint8)
    tracks = {
        1: {"bbox": (10, 10, 30, 30), "zone": "right", "trail": [(15, 15), (20, 20)]}
    }
    draw_overlays(
        frame,
        tracks,
        show_ids=True,
        show_track_lines=True,
        show_lines=True,
        line_orientation="vertical",
        line_ratio=0.5,
        show_counts=True,
        in_count=1,
        out_count=2,
        face_boxes=[(60, 60, 80, 80)],
    )
    assert (frame[0, 50] == np.array([255, 0, 0])).all()
    assert frame[10, 10].any()
    assert frame[30, 10].any()
    assert frame[60, 60].any()


def test_draw_overlays_face_boxes_only():
    frame = np.zeros((50, 50, 3), dtype=np.uint8)
    draw_overlays(
        frame,
        {},
        show_ids=False,
        show_track_lines=False,
        show_lines=False,
        line_orientation="vertical",
        line_ratio=0.5,
        show_counts=False,
        in_count=0,
        out_count=0,
        face_boxes=[(5, 5, 20, 20)],
    )
    assert frame[5, 5].any()
    assert frame[5, 19].any()


def test_draw_overlays_skips_invalid_entries():
    frame = np.zeros((40, 40, 3), dtype=np.uint8)
    tracks = {
        1: {
            "bbox": (np.nan, 0, 10, 10),
            "zone": "right",
            "trail": [(np.nan, 0), (5, 5)],
        }
    }
    draw_overlays(
        frame,
        tracks,
        show_ids=True,
        show_track_lines=True,
        show_lines=False,
        line_orientation="vertical",
        line_ratio=0.5,
        show_counts=False,
        in_count=0,
        out_count=0,
        face_boxes=[(0, 0, np.inf, np.inf)],
    )
    assert not frame.any()


def test_draw_counting_line_helper():
    frame = np.zeros((10, 10, 3), dtype=np.uint8)
    _draw_counting_line(frame, "vertical", 0.5)
    assert (frame[0, 5] == np.array([255, 0, 0])).all()


def test_draw_track_helper():
    frame = np.zeros((100, 100, 3), dtype=np.uint8)
    info = {
        "id": 1,
        "bbox": (10, 10, 30, 30),
        "zone": "right",
        "trail": [(15, 15), (20, 20)],
    }
    _draw_track(frame, info, 1.0, True, True)
    assert (frame[10, 10] == np.array([0, 255, 0])).all()
    assert (frame[15, 15] == np.array([0, 0, 255])).all()


def test_draw_counts_helper():
    frame = np.zeros((100, 100, 3), dtype=np.uint8)
    _draw_counts(frame, 1, 2)
    assert frame[20, 13].any()
    assert frame[60, 13].any()
