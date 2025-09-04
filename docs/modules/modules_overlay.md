# modules_overlay
[Back to Architecture Overview](../README.md)

## Purpose
Purpose: Overlay module. Debug overlays use solid LINE_8 drawing without
alpha blending or antialiasing, and labels are limited to a single line
of text with no shadows or rounded corners.

## Key Classes
None

## Key Functions
 - **draw_overlays(frame, tracks, show_ids, show_track_lines, show_lines, line_orientation, line_ratio, show_counts, in_count, out_count)** - Draw tracking debug overlays on the frame.

## Inputs and Outputs
Refer to function signatures above for inputs and outputs. When any debug flag (lines, IDs, track lines, or counts) is enabled the processed frame is streamed via `/stream/preview/{cam_id}`; otherwise the dashboard requests `/stream/clean/{cam_id}`. Client-side scripts update the feed URL when these settings change.

## Redis Keys
None

## Dependencies
- cv2
- typing
