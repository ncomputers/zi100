# modules_model_registry
[Back to Architecture Overview](../README.md)

## Purpose
Shared registry for heavy ML models to avoid redundant loads.

## Key Classes
None

## Key Functions
- **_log_mem(note, device)** - 
- **_resolve_device(device)** - 
- **get_yolo(path, device)** - Return a cached YOLO model for ``path`` on ``device``.
- **get_insightface(name, det_size)** - Return a cached InsightFace ``FaceAnalysis`` instance.

## Inputs and Outputs
Refer to function signatures above for inputs and outputs.

## Redis Keys
- `cuda:0`

## Dependencies
- __future__
- config
- loguru
- psutil
- typing
