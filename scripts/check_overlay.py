from pathlib import Path
import sys


import cv2
import numpy as np
sys.path.append(str(Path(__file__).resolve().parent.parent))


from modules.overlay import draw_overlays


def main() -> None:
    """Create a dummy frame and draw debug overlays."""
    # Create a blank black image
    frame = np.zeros((480, 640, 3), dtype=np.uint8)

    # Example track to visualize IDs and track lines
    tracks = {
        1: {
            "bbox": (50, 100, 150, 200),
            "trail": [(100, 150), (120, 160), (140, 170)],
            "zone": "left",
        }
    }

    draw_overlays(
        frame,
        tracks,
        show_ids=True,
        show_track_lines=True,
        show_lines=True,
        line_orientation="horizontal",
        line_ratio=0.5,
        show_counts=True,
        in_count=1,
        out_count=0,
    )

    output_path = "scripts/check_overlay_output.jpg"
    cv2.imwrite(output_path, frame)
    print(f"Overlay image saved to {output_path}")


if __name__ == "__main__":
    main()
