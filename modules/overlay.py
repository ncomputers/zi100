"""Drawing routines for overlays on video frames."""

import math
from typing import Dict, List, Tuple

import cv2


def _sanitize_bbox(
    bbox: Tuple[float, float, float, float], w: int, h: int
) -> Tuple[int, int, int, int] | None:
    """Validate and clamp a bounding box to frame bounds."""
    x1, y1, x2, y2 = bbox
    if not all(math.isfinite(v) for v in bbox):
        return None
    xi1, yi1, xi2, yi2 = map(int, [x1, y1, x2, y2])
    xi1 = max(0, min(xi1, w - 1))
    yi1 = max(0, min(yi1, h - 1))
    xi2 = max(0, min(xi2, w - 1))
    yi2 = max(0, min(yi2, h - 1))
    if xi1 >= xi2 or yi1 >= yi2:
        return None
    return xi1, yi1, xi2, yi2


def _sanitize_point(x: float, y: float, w: int, h: int) -> Tuple[int, int] | None:
    """Validate and clamp a point to frame bounds."""
    if not (math.isfinite(x) and math.isfinite(y)):
        return None
    xi, yi = int(x), int(y)
    xi = max(0, min(xi, w - 1))
    yi = max(0, min(yi, h - 1))
    return xi, yi


def _get_text_size(text: str, font, scale: float, thickness: int) -> Tuple[int, int]:
    """Return the width and height of ``text`` for given font settings."""
    return cv2.getTextSize(text, font, scale, thickness)[0]


def _draw_counting_line(frame, line_orientation: str, line_ratio: float) -> None:
    """Draw the counting line on ``frame``."""
    h, w = frame.shape[:2]
    line_pos = int((h if line_orientation == "horizontal" else w) * line_ratio)
    if line_orientation == "horizontal":
        cv2.line(frame, (0, line_pos), (w, line_pos), (255, 0, 0), 2)
    else:
        cv2.line(frame, (line_pos, 0), (line_pos, h), (255, 0, 0), 2)


def _draw_track(
    frame, info: Dict, scale: float, show_ids: bool, show_track_lines: bool
) -> None:
    """Render a single track on ``frame``."""
    h, w = frame.shape[:2]
    bbox_raw = info.get("bbox", (0, 0, 0, 0))
    if scale != 1.0:
        bbox_raw = tuple(v * scale for v in bbox_raw)
    bbox = _sanitize_bbox(bbox_raw, w, h)

    color = (0, 255, 0) if info.get("zone") == "right" else (0, 0, 255)
    if show_track_lines and bbox:
        x1, y1, x2, y2 = bbox
        cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2, lineType=cv2.LINE_8)
    if show_track_lines:
        trail = info.get("trail", [])
        if not isinstance(trail, (list, tuple)):
            trail = []
        for i in range(1, len(trail)):
            x1, y1 = trail[i - 1]
            x2, y2 = trail[i]
            if scale != 1.0:
                p1 = _sanitize_point(x1 * scale, y1 * scale, w, h)
                p2 = _sanitize_point(x2 * scale, y2 * scale, w, h)
            else:
                p1 = _sanitize_point(x1, y1, w, h)
                p2 = _sanitize_point(x2, y2, w, h)
            if p1 and p2:
                cv2.line(frame, p1, p2, (0, 0, 255), 2)
    if show_ids and bbox:
        x1, y1, _, _ = bbox
        label = info.get("group", "")
        conf = info.get("conf")
        tid = info.get("id")
        parts = [f"ID {tid}"]
        if conf is not None:
            parts.append(f"{conf:.2f}")
        if label:
            parts.append(str(label))
        text = " ".join(parts)
        cv2.putText(
            frame,
            text,
            (x1, y1 - 10),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.5,
            color,
            2,
            lineType=cv2.LINE_8,
        )


def _draw_counts(frame, in_count: int, out_count: int) -> None:
    """Display entry and exit counts on ``frame``."""
    enter_text = f"Entering: {in_count}"
    _get_text_size(enter_text, cv2.FONT_HERSHEY_SIMPLEX, 1, 2)
    cv2.putText(
        frame,
        enter_text,
        (10, 30),
        cv2.FONT_HERSHEY_SIMPLEX,
        1,
        (0, 255, 0),
        2,
        lineType=cv2.LINE_8,
    )
    exit_text = f"Exiting: {out_count}"
    _get_text_size(exit_text, cv2.FONT_HERSHEY_SIMPLEX, 1, 2)
    cv2.putText(
        frame,
        exit_text,
        (10, 70),
        cv2.FONT_HERSHEY_SIMPLEX,
        1,
        (0, 0, 255),
        2,
        lineType=cv2.LINE_8,
    )


# draw_overlays routine
def draw_overlays(
    frame,
    tracks: Dict[int, dict],
    show_ids: bool,
    show_track_lines: bool,
    show_lines: bool,
    line_orientation: str,
    line_ratio: float,
    show_counts: bool,
    in_count: int,
    out_count: int,
    face_boxes: List[Tuple[int, int, int, int]] | None = None,
    *,
    scale: float = 1.0,
) -> None:
    """Draw tracking debug overlays on the frame.

    Parameters
    ----------
    frame: np.ndarray
        Image buffer to draw on.
    tracks: Dict[int, dict]
        Active DeepSort tracks.
    show_ids, show_track_lines, show_lines, show_counts: bool
        Flags controlling which overlays to render.
    line_orientation: str
        "horizontal" or "vertical" line direction.
    line_ratio: float
        Position of the counting line as a ratio of the frame size.
    in_count, out_count: int
        Current entry/exit counts.
    face_boxes: List[Tuple[int, int, int, int]] | None, optional
        Bounding boxes of detected faces to draw when provided.
    scale: float, optional
        Factor to apply when drawing on a resized frame. Coordinate inputs
        are multiplied by this value before rendering.

    """
    h, w = frame.shape[:2]
    if show_lines:
        _draw_counting_line(frame, line_orientation, line_ratio)

    for tid, info in tracks.items():
        track_info = {"id": tid, **info}
        _draw_track(frame, track_info, scale, show_ids, show_track_lines)

    if show_counts:
        _draw_counts(frame, in_count, out_count)

    if face_boxes:
        for box in face_boxes:
            if scale != 1.0:
                box = tuple(v * scale for v in box)
            bbox = _sanitize_bbox(box, w, h)
            if bbox:
                x1, y1, x2, y2 = bbox
                cv2.rectangle(
                    frame, (x1, y1), (x2, y2), (255, 255, 0), 2, lineType=cv2.LINE_8
                )
