# modules_face_db
[Back to Architecture Overview](../README.md)

## Purpose
Purpose: Face db module.

## Key Classes
None

## Key Functions
- **init(cfg, r)** - Initialize shared objects and FAISS index.
- **add_face(visitor_id, image_bytes, merge_on_match=False, threshold=0.95)** - Detect a single face and store its embedding under ``visitor_id`` while optionally merging with existing matches.
- **add_face_if_single_detected(image_bytes, person_id)** - Wrapper used by API endpoints to safely add a face if exactly one is detected.
- **insert(image_bytes, person_id, source, merge_on_match=False, threshold=0.95)** - Insert a face embedding without quality checks. Performs a duplicate search using the given ``threshold`` and merges into an existing record when ``merge_on_match`` is ``True``.
- **delete_face(person_id)** - Remove a face embedding and update the known IDs set.
- **search_faces(image_bytes, top_k)** - Return top-k matches from FAISS with cosine similarity.

## Live Frame Processing

The `/process_frame` endpoint accepts JSON payloads containing a base64 encoded
image along with `scaleFactor` and `minNeighbors` parameters. It returns an
array of detected faces with bounding boxes, name, id and confidence score.
Only send frames from trusted clients over secure connections since the
endpoint processes arbitrary images.

## Face Quality Endpoint

`POST /face_quality` accepts a base64-encoded image and evaluates
pose, blur, and brightness for the first detected face. The response
includes raw metric values and an aggregated `quality` score in the
range 0-1. Clients can use this to gate image uploads before saving to
the database.

## Camera Snapshot Endpoint

`GET /process_camera/{cam_id}` captures a single frame from the specified
camera and runs the same face-recognition pipeline used for live frames.
The response contains a base64-encoded JPEG along with detected faces:

```json
{
  "image": "<base64 jpg>",
  "faces": [{"box": [x, y, w, h], "name": "...", "id": "...", "confidence": 0.0}]
}
```

The Face DB management page provides a **Camera Test** tab that leverages
this endpoint. Selecting a camera will periodically fetch snapshots and
overlay recognition results for quick diagnostics.

## Duplicate Detection Workflow

Both ``add_face`` and ``insert`` run a similarity search against the current
database before committing a new embedding. When a match above the specified
``threshold`` (default ``0.95``) is found the call returns the match details.
Setting ``merge_on_match=True`` will average the new embedding into the
existing record automatically.

## Inputs and Outputs
Refer to function signatures above for inputs and outputs.

## Redis Keys
- `face:known:`
- `face:known_ids`

## Dependencies
- __future__
- cv2
- json
- loguru
- numpy
- pathlib
- psutil
- redis
- time
- typing
