# modules_overlay
[Back to Architecture Overview](../README.md)

## Purpose
Purpose: Overlay module. Debug overlays use solid LINE_8 drawing without
alpha blending or antialiasing, and labels are limited to a single line
of text with no shadows or rounded corners.

## Key Classes
None

## Key Functions
- **draw_overlays(frame, tracks, show_ids, show_track_lines, show_lines, line_orientation, line_ratio, show_counts, in_count, out_count, face_boxes=None)** - Draw tracking debug overlays and optional face bounding boxes on the frame.

## Inputs and Outputs
Refer to function signatures above for inputs and outputs. When any debug flag (lines, IDs, track lines, counts, or face boxes) is enabled the processed frame is streamed via `/stream/{cam_id}`; otherwise the dashboard requests `/stream/{cam_id}?raw=1`. Client-side scripts update the feed URL when these settings change.

## Redis Keys
None

## Dependencies
- cv2
- typing
