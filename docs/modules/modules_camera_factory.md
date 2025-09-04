# modules_camera_factory
[Back to Architecture Overview](../README.md)

## Purpose
Factory helpers for opening camera streams. The function prioritizes
FFmpeg and falls back to GStreamer when initialization fails.

## Key Classes
- **StreamUnavailable** - Raised when no capture backend can provide frames.

## Key Functions
- **open_capture(src, cam_id, src_type=None, resolution, rtsp_transport, stream_mode, use_gpu, capture_buffer, local_buffer_size=1, backend_priority=None, ffmpeg_flags=None, pipeline=None, profile=None, ffmpeg_reconnect_delay=None, ready_frames=1, ready_duration=None, ready_timeout=15.0, for_display=False)** - Return a capture object for the configured stream, trying FFmpeg first and using GStreamer as a fallback. The stream is considered ready only after ``ready_frames`` consecutive frames or ``ready_duration`` seconds of continuous frames are read within ``ready_timeout`` seconds (defaults: 1 frame, 15 seconds). When ``for_display`` is ``False``, the ``opencv`` backend is skipped. ``src_type`` defaults to the scheme-derived value and ``ffmpeg_reconnect_delay`` falls back to the ``ffmpeg_reconnect_delay`` setting in ``config.json``. ``local_buffer_size`` controls the internal frame queue for USB cameras.

## Backend Selection and Fallback
`open_capture` attempts capture backends in priority order. By default the order is:

1. FFmpeg
2. GStreamer
3. OpenCV (only when ``for_display=True``)

When ``config["enable_gstreamer"]`` is ``false``, GStreamer is removed from this list before any backends are attempted. When ``for_display`` is ``False``, ``opencv`` is removed as well, keeping headless deployments free of GUI dependencies.

You can override the order with the ``backend_priority`` argument or a ``backend`` override stored in Redis. If a backend fails to initialize or cannot satisfy the readiness criteria within ``ready_timeout`` seconds, the factory logs the error, stores the failure reason in ``camera_debug:<cam_id>``, and moves to the next backend. ``FFmpegCameraStream`` itself cycles through transports defined in ``retry_transports`` before other backends are attempted.
When ``config["enable_gstreamer"]`` is ``False``, GStreamer is omitted from backend selection entirely.

### Pipeline profiles

Reusable capture settings can be defined in ``config.json`` under ``pipeline_profiles``. Each profile may specify a complete pipeline or command for its backend:

```json
"pipeline_profiles": {
  "gst_full": {
    "label": "Full GStreamer",
    "backend": "gstreamer",
    "pipeline": "rtspsrc location={url} latency=0 ! decodebin ! videoconvert ! video/x-raw,format=BGR ! appsink"
  },
  "ffmpeg_copy": {
    "label": "FFmpeg copy",
    "backend": "ffmpeg",
    "command": "-rtsp_transport tcp -i {url} -an"
  }
}
```

Selecting a profile via ``open_capture(..., profile="gst_full")`` applies its backend and full pipeline or command. The ``{url}`` placeholder is substituted with the camera address at runtime.


#### Precedence

``open_capture`` resolves settings in this order:

1. Explicit arguments
2. Redis overrides
3. Profile defaults

### Full pipeline profiles

The ``pipeline_profiles`` block can also describe complete pipelines for each
backend. The ``{url}`` placeholder below represents the camera's RTSP/HTTP
address.

#### GStreamer

```json
"pipeline_profiles": {
  "gst_full": {
    "label": "GStreamer TCP example",
    "backend": "gstreamer",
    "pipeline": "rtspsrc location={url} protocols=tcp latency=0 ! decodebin ! videoconvert ! video/x-raw,format=BGR ! appsink"
  }
}
```

Command-line equivalent:

```bash
gst-launch-1.0 rtspsrc location=rtsp://user:pass@cam/stream protocols=tcp latency=0 ! decodebin ! videoconvert ! video/x-raw,format=BGR ! fakesink
```

Replace ``rtsp://user:pass@cam/stream`` with your camera URL.

#### FFmpeg

```json
"pipeline_profiles": {
  "ffmpeg_full": {
    "label": "FFmpeg TCP example",
    "backend": "ffmpeg",
    "ffmpeg_flags": "-rtsp_transport tcp -flags low_delay -fflags nobuffer"
  }
}
```

Command-line equivalent:

```bash
ffplay -rtsp_transport tcp -flags low_delay -fflags nobuffer {url}
```

Replace ``{url}`` with your stream address.

#### OpenCV

```json
"pipeline_profiles": {
  "opencv_full": {
    "label": "OpenCV example",
    "backend": "opencv",
    "resolution": "720p"
  }
}
```

Command-line equivalent:

```bash
python - <<'PY'
import cv2
cap = cv2.VideoCapture("{url}")
while True:
    ret, frame = cap.read()
    if not ret:
        break
    cv2.imshow("preview", frame)
    if cv2.waitKey(1) == 27:
        break
cap.release()
cv2.destroyAllWindows()
PY
```

Replace ``{url}`` with your camera URL.

## Inputs and Outputs
Refer to function signatures above for inputs and outputs.

## Redis Keys
- `camera_debug:<cam_id>` – JSON record describing the last initialization failure.

### `camera_debug` format
When initialization fails the factory writes a structured record to Redis. It
contains a timestamp, the backend that failed, and a human readable message:

```json
{
  "ts": "2024-05-01T12:00:00Z",
  "backend": "ffmpeg",
  "message": "FFmpeg (tcp) stream failed: no frames within timeout"
}
```

Retrieve a record with:

```bash
redis-cli get camera_debug:lobby
```

Example output for an authentication error:

```json
{
  "ts": "2024-05-01T12:00:00Z",
  "backend": "gstreamer",
  "message": "GStreamer init error: unauthorized (401)"
}
```

## Dependencies
- cv2
- ffmpeg_stream
- gstreamer_stream
- loguru
- opencv_stream
- time

## Examples

### Switching between TCP and UDP

```python
from modules.camera_factory import open_capture

cap, transport = open_capture(
    "rtsp://user:pass@cam/stream",
    cam_id="lobby",
    src_type="rtsp",
    rtsp_transport="udp",  # use UDP instead of TCP
)
```

### Using a full GStreamer pipeline

Define the pipeline in ``pipeline_profiles`` as shown above, then select it when opening the stream:

```python
cap, _ = open_capture(
    "rtsp://user:pass@cam/stream",
    cam_id="gate",
    profile="gst_full",
)
```

### Diagnosing common errors

When a backend fails, the reason is stored in Redis. A common message is
`no frames within timeout`. To troubleshoot:

1. **Check network reachability** – use tools like `ping` or `traceroute` to
   ensure the host is reachable.
2. **Verify credentials** – `401` or `403` responses indicate authentication
   problems; confirm the username and password.
3. **Switch RTSP transport** – toggle the `rtsp_transport` between `tcp` and
   `udp` to see which one the camera supports.

Retrieve the latest failure record with:

```bash
redis-cli get camera_debug:lobby
```

Authentication problems often return `401` or `403` errors. Messages like
`No route to host` or repeated timeouts indicate network reachability issues.
Use `ping` or `traceroute` to verify connectivity.

### Adjusting readiness requirements

```python
# Require five consecutive frames
cap, transport = open_capture(
    "rtsp://user:pass@cam/stream",
    cam_id="lobby",
    ready_frames=5,
    ready_timeout=10.0,  # wait up to 10s for 5 consecutive frames
)

# Or require 2 seconds of steady frames
cap, transport = open_capture(
    "rtsp://user:pass@cam/stream",
    cam_id="lobby",
    ready_frames=0,
    ready_duration=2.0,
    ready_timeout=10.0,  # wait up to 10s for 2 seconds of frames
)
```

