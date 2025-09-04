"""Helpers for exporting PPE reports."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Iterable, Mapping

from openpyxl import Workbook
from openpyxl.drawing.image import Image as XLImage

BASE_DIR = Path(__file__).resolve().parent.parent


def build_ppe_workbook(rows: Iterable[Mapping]) -> Workbook:
    """Create a workbook for PPE report rows.

    Each row should contain keys: ``time``, ``cam_id``, ``track_id``,
    ``status``, ``conf``, ``color`` and optional ``image`` pointing to
    an image file relative to the project root.
    """
    wb = Workbook()
    ws = wb.active
    ws.append(["Time", "Camera", "Track", "Status", "Conf", "Color", "Image"])
    for row in rows:
        ws.append(
            [
                row.get("time", ""),
                row.get("cam_id", ""),
                row.get("track_id", ""),
                row.get("status", ""),
                round(float(row.get("conf", 0)), 2),
                row.get("color") or "",
            ]
        )
        img_path = row.get("image")
        if img_path:
            img_file = os.path.join(BASE_DIR, str(img_path).lstrip("/"))
            if os.path.exists(img_file):
                try:
                    img = XLImage(img_file)
                    img.width = 80
                    img.height = 60
                    ws.add_image(img, f"G{ws.max_row}")
                except Exception:
                    # Skip image if it cannot be processed
                    pass
    return wb
