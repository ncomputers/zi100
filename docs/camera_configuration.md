# Camera configuration

The camera factory waits for a stream to deliver frames before declaring it ready.

## ready_timeout

`ready_timeout` sets the maximum number of seconds to wait for frames during
initialization. If the stream fails to provide enough frames within this period,
initialization falls back to the next backend or raises an error. The default is
**15.0** seconds.

For slower or high-latency RTSP feeds, especially those on congested networks or
with low frame rates, increase ``ready_timeout`` to give the stream more time to
start. Values of 30 seconds or more are common for remote cameras. The timeout
can be adjusted globally in ``config.json`` or per camera via the management UI
to accommodate individual feeds.

## ready_frames

`ready_frames` sets the number of consecutive frames required before a stream is
considered ready. Set it to ``0`` to rely solely on ``ready_duration``. The
default is **1** frame.

Example configuration:

```json
{
  "ready_frames": 5,
  "ready_timeout": 10.0
}
```
