# routers_cameras
[Back to Architecture Overview](../README.md)

## Purpose
Camera management routes.

## Key Classes
None

## Key Functions
- **init_context(config, cameras, trackers, redis_client, templates_path)** - 
- **_expand_ppe_tasks(tasks)** - Ensure each selected PPE class includes its paired absence/presence.

## Inputs and Outputs
Refer to function signatures above for inputs and outputs.

## Redis Keys
- `rtsp://`

## Dependencies
- __future__
- config
- core.config
- core.tracker_manager
- cv2
- fastapi
- fastapi.responses
- fastapi.templating
- json
- modules.ffmpeg_stream
- modules.gstreamer_stream
- modules.utils
- typing
- utils
