# Camera preview endpoint

The `/cameras/test` route can start a temporary preview stream from an RTSP
camera. Sending a POST request with `{"url": "<rtsp-url>", "stream": true}`
launches an FFmpeg (or GStreamer, depending on configuration) background
process that converts the feed to an MJPEG stream.

By default the stream is returned at its native resolution. Supplying `width`
and `height` values in the request body scales the preview to the specified
dimensions.

The response includes a `stream_url` pointing to
`/cameras/test/stream/{id}` which serves the MJPEG data over HTTPS. The stream
response sets `Access-Control-Allow-Origin: *` so it can be embedded from other
origins.

Streams are transient and stop when the client disconnects.

## Example

```bash
curl -X POST https://example.com/cameras/test \
  -H 'Content-Type: application/json' \
  -d '{"url":"rtsp://camera/stream","stream": true}'
```

```json
{"stream_url": "https://example.com/cameras/test/stream/abc123"}
```

## Browser preview controls

When using the in‑browser photo uploader, a brightness slider becomes available
as soon as the camera is active. Moving the control applies a CSS
`brightness()` filter to the live video element so users can fine‑tune exposure
before capturing an image.

# Camera probe endpoint

The `/cameras/probe` route evaluates an RTSP stream and recommends the
best transport and hardware acceleration settings. It is backed by the
`modules.stream_probe.probe_stream` helper which first runs `ffprobe` to
collect codec, resolution and frame rate metadata. It then launches short
`ffmpeg` trials over TCP and UDP, with and without hardware acceleration,
to measure the effective frames per second (FPS) each combination can
achieve. The combination producing the most decoded frames is returned.

Send a POST request with `{ "url": "<rtsp-url>" }` to receive a summary of
the detected metadata and the selected transport.

## Example

```bash
curl -X POST https://example.com/cameras/probe \
  -H 'Content-Type: application/json' \
  -d '{"url":"rtsp://camera/stream"}'
```

```json
{
  "metadata": {
    "codec": "h264",
    "profile": "Baseline",
    "width": 1280,
    "height": 720,
    "pix_fmt": "yuv420p",
    "bit_rate": "1350000",
    "avg_frame_rate": "25/1",
    "r_frame_rate": "25/1",
    "time_base": "1/90000",
    "nominal_fps": 25.0
  },
  "effective_fps": 24.8,
  "transport": "tcp",
  "hwaccel": true
}
```

## CLI frame capture

Use `scripts/rtsp_capture_frame.py` to probe a camera and save a single frame.

```bash
python scripts/rtsp_capture_frame.py rtsp://user:pass@host/stream
# specify output path
python scripts/rtsp_capture_frame.py rtsp://camera/stream -o snapshot.jpg
```

The script reports the stream's resolution and logs the image path on success.

