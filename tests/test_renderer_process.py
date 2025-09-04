import numpy as np

from modules.renderer import RendererProcess


def test_renderer_writes_overlay():
    shape = (10, 10, 3)
    renderer = RendererProcess(shape)
    renderer.frame[:] = 0
    tracks = {1: {"bbox": (1, 1, 5, 5)}}
    renderer.queue.put(
        {
            "tracks": tracks,
            "flags": {
                "show_ids": False,
                "show_track_lines": True,
                "show_lines": False,
                "show_counts": False,
                "show_face_boxes": False,
            },
            "line_orientation": "vertical",
            "line_ratio": 0.5,
            "in_count": 0,
            "out_count": 0,
            "face_boxes": None,
        }
    )
    renderer.queue.put(None)
    renderer.process.join()
    assert renderer.output.any()
    renderer.close()
