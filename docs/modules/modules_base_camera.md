# modules_base_camera
[Back to Architecture Overview](../README.md)

## Purpose
Threaded frame capture base with a small rolling buffer.

## Key Classes
- **BaseCameraStream** - Generic threaded capture with a small rolling buffer.

Buffer size ``N`` adds roughly ``N / fps`` seconds of latency but keeps the
stream smooth when inference stalls.

## Default Backend Order
When ``BaseCameraStream`` derivatives are selected via
``open_capture``, the library now attempts FFmpeg first and falls back to
GStreamer. OpenCV is reserved for on-demand dashboard display only.

## Key Functions
None

## Inputs and Outputs
Refer to function signatures above for inputs and outputs.

## Redis Keys
None

## Dependencies
- __future__
- collections
- numpy
- threading
- time
- typing
