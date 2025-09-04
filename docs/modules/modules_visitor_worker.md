# modules_visitor_worker
[Back to Architecture Overview](../README.md)

## Purpose
Background worker for visitor face recognition. Uses the shared
`VISITOR_DISABLED_MSG` constant for consistent logging when the feature is
disabled.

## Key Classes
- **VisitorRecord** - 
- **VisitorWorker** - Continuously process frames for visitor recognition.

## Key Functions
- **_blur_score(img)** - 

## Inputs and Outputs
Refer to function signatures above for inputs and outputs.

## Redis Keys
- `face:known:`
- `face:known_ids`
- `face:raw:`
- `visitor_log:index`

## Dependencies
- __future__
- base64
- collections
- config
- cv2
- dataclasses
- json
- numpy
- pathlib
- psutil
- redis.exceptions
- threading
- time
- typing
- utils.gpu
- utils.logging
- utils.redis
- uuid
- routers.visitor_utils
