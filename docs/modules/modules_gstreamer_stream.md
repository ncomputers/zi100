# modules_gstreamer_stream
[Back to Architecture Overview](../README.md)

## Purpose
Camera stream wrapper using GStreamer pipelines.

## Key Classes
- **GstCameraStream** - Capture video frames using a GStreamer pipeline.

## Key Functions
- **_ensure_gst()** - Attempt to import GStreamer bindings if enabled in config.

## Inputs and Outputs
Refer to function signatures above for inputs and outputs.

## Redis Keys
None

## Dependencies
- __future__
- base_camera
- config
- cv2
- numpy
- typing
- utils.logging

## Configuration
- `enable_gstreamer` – when `false`, skips importing GStreamer bindings.

## Custom Pipelines
``GstCameraStream`` can run a complete pipeline provided by ``open_capture``.
Define reusable pipelines in ``config.json`` under ``pipeline_profiles``:

```json
"pipeline_profiles": {
  "gst_full": {
    "backend": "gstreamer",
    "pipeline": "rtspsrc location={url} ! decodebin ! videoconvert ! video/x-raw,format=BGR ! appsink"
  }
}
```

```python
from modules.camera_factory import open_capture

cap, _ = open_capture(
    "rtsp://user:pass@cam/stream",
    cam_id="lobby",
    profile="gst_full",
)

# Log the expanded pipeline for debugging
from loguru import logger
logger.info("GStreamer pipeline: {}", cap.pipeline)
```

The ``{url}`` placeholder is replaced with the camera address at runtime.

## Troubleshooting
When used via ``open_capture``, initialization errors are logged and the
reason can be read from ``camera_debug:<cam_id>`` in Redis. Ensure the camera
credentials are correct and that the host is reachable over the network.
