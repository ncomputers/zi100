# Global CPU limit

Set `cpu_limit_percent` in `config.json` to bind the application to a fraction
of CPU cores and cap threads used by BLAS libraries:

```json
{
  "cpu_limit_percent": 75
}
```

# Camera configuration overrides

Per-camera settings can be stored in the `camera:{id}` hash or sent via the
Cameras API to customize how each stream is processed. The snippets below show
how to override `frame_skip` and FFmpeg flags for a single camera.

## JSON

```json
{
  "frame_skip": 5,
  "ffmpeg_flags": "-flags low_delay -fflags nobuffer"
}
```

## YAML

```yaml
frame_skip: 5
ffmpeg_flags: "-flags low_delay -fflags nobuffer"
```

Apply these overrides to the desired camera to adjust processing frequency and
stream latency.
