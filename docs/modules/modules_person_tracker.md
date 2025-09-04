# modules_person_tracker
[Back to Architecture Overview](../README.md)

## Purpose
Purpose: Person tracker module.

## Key Classes
- **PersonTracker** - Tracks entry and exit counts using YOLOv8 and DeepSORT.

## Key Functions
None

## Retry Throttling
The capture loop tracks consecutive frame read failures and logs each
failure at warning level. Between retries it sleeps for a fixed 0.1
seconds, so the retry interval is constant. If the failure count exceeds a
configured threshold, the capture is restarted.

## Inputs and Outputs
Refer to function signatures above for inputs and outputs.

## Redis Keys
- `person_tracker:cam:<id>:in`
- `person_tracker:cam:<id>:out`
- `person_tracker:cam:<id>:date`

## Dependencies
- __future__
- camera_factory
- collections
- core.config
- cv2
- datetime
- duplicate_filter
- ffmpeg_stream
- gstreamer_stream
- json
- loguru
- modules.profiler
- numpy
- overlay
- pathlib
- psutil
- queue
- threading
- time
- typing
- utils
- utils.redis
- uuid
