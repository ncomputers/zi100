"""Drawing helpers for overlays on image frames."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class OverlayThrottler:
    """Decide whether to render debug overlays for a frame."""

    every_n: int = 1
    min_ms: int = 0
    frame_idx: int = 0
    last_draw_ms: int | None = None

    # should_draw routine
    def should_draw(self, now_ms: int) -> bool:
        """Return ``True`` if overlays should be drawn for this frame."""

        draw = self.frame_idx % max(1, self.every_n) == 0
        if draw and self.last_draw_ms is not None:
            if now_ms - self.last_draw_ms < self.min_ms:
                draw = False
        if draw:
            self.last_draw_ms = now_ms
        self.frame_idx += 1
        return draw
