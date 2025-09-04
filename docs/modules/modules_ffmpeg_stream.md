# modules_ffmpeg_stream
[Back to Architecture Overview](../README.md)

## Purpose
Camera stream using FFmpeg with a rolling buffer.

## Default Pipeline
The default invocation is:

```bash
ffmpeg -rtsp_transport tcp \
       -fflags nobuffer+discardcorrupt \
       -flags low_delay \
       -fflags +genpts \
       -analyzeduration 1000000 \
       -probesize 500000 \
       -i {url} -vcodec rawvideo -pix_fmt bgr24 -f rawvideo -
```

Use `ffmpeg_flags` in `config.json` to append custom arguments. The global `frame_skip` option drops frames before they reach this stream to save resources.

When `ffmpeg_high_watermark` is configured, the stream attempts to enable FFmpeg's
`-drop` option to discard frames when buffers fill. If the running FFmpeg build
does not advertise `-drop` support (checked via `ffmpeg -h`), a warning is logged
and the watermark flags are skipped.

For HTTP(S) sources the command automatically includes reconnection flags:

```bash
-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max <sec>
```

`<sec>` defaults to the `ffmpeg_reconnect_delay` configuration value and
ensures transient network issues are retried without restarting the process.

## Key Classes
- **FFmpegCameraStream** - Capture frames using FFmpeg and keep only the latest N.

## Key Functions
None

## Transport Selection
``FFmpegCameraStream`` accepts a ``transport`` argument which maps to
FFmpeg's ``-rtsp_transport`` option. A ``retry_transports`` list
(default ``["tcp", "udp"]``) controls the order of transports to try
when no frames arrive. The successful choice is available via the
``successful_transport`` property. UDP can be explicitly requested:

```python
FFmpegCameraStream(
    "rtsp://user:pass@cam/stream",
    width=1280,
    height=720,
    transport="udp",
    buffer_size=3,
    cam_id="lot",
)
```

When used via ``open_capture``, the stream automatically cycles through
``retry_transports`` before falling back to other backends.

## Custom Commands
Full FFmpeg invocations can be configured in ``pipeline_profiles``:

```json
"pipeline_profiles": {
  "ffmpeg_copy": {
    "backend": "ffmpeg",
    "command": "-rtsp_transport tcp -i {url} -vf scale=1280:-1 -an"
  }
}
```

Use the profile with ``open_capture(..., profile="ffmpeg_copy")``. The ``{url}`` placeholder is replaced with the camera address at runtime.

## Troubleshooting
If initialization fails, inspect ``camera_debug:<cam_id>`` in Redis for the
error message. Authentication failures usually include ``401`` or ``403`` codes.
Network issues may show timeouts or ``No route to host`` errors. ``short read``
or ``Connection reset`` messages indicate the camera closed the connection;
try a different ``rtsp_transport`` or lower bandwidth.

## Inputs and Outputs
Refer to function signatures above for inputs and outputs.

## Redis Keys
- `rtsp://`
- `v:0`

## Dependencies
- __future__
- base_camera
- loguru
- numpy
- select
- subprocess
- time
- typing
- ffmpeg (CLI)
- ultralytics
