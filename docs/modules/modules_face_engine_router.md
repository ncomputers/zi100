# modules_face_engine_router
[Back to Architecture Overview](../README.md)

## Purpose
FastAPI routes exposing face engine capabilities.

## Key Classes
None

## Key Functions
- **_read_image(image, image_base64)** - Async helper to read uploaded or base64 image data.
- **insert_face(person_id, image, source="upload", merge_on_match=False, threshold=0.95)** - Insert a face image into the
  database without checks. When ``merge_on_match`` is enabled the uploaded face will
  be merged with any existing match above ``threshold``; otherwise match details are returned.
- **search_face(image, top_k=1, threshold=0.95)** - Return up to ``top_k`` matches from the face database using the provided ``threshold``.

## Inputs and Outputs
Refer to function signatures above for inputs and outputs.

## Redis Keys
None

## Dependencies
- __future__
- base64
- cv2
- detector
- embedder
- fastapi
- fastapi.responses
- modules
- numpy
- time
- typing
