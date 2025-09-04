# modules_face_engine_utils
[Back to Architecture Overview](../README.md)

## Purpose
Helper functions for the face engine.

## Key Classes
None

## Key Functions
- **load_image(data)** - Load an image from raw bytes or base64 string.
- **crop_face(image, bbox)** -
- **resize(image, max_size)** -
- **is_blurry(image, threshold)** -
- **face_count(image, detector)** -

## Thresholds, defaults, and usage
The face engine centralizes common thresholds in `config.FaceThresholds`.
These settings can be overridden through configuration and are consumed by
helpers such as `is_blurry` and the face database utilities.

| Name | Default | Usage |
| ---- | ------- | ----- |
| `recognition_match` | `0.6` | Minimum similarity score required to consider two faces a match during recognition. Override with `face_match_thresh`. |
| `db_duplicate` | `0.95` | Treat two face embeddings as the same person when adding to the database. Override with `face_db_dup_thresh`. |
| `duplicate_suppression` | `0.5` | Suppress repeated detections of the same face to reduce duplicates. Override with `face_duplicate_thresh`. |
| `blur_detection` | `100.0` | Variance of Laplacian below this value marks an image as blurry and skips processing. Override with `blur_detection_thresh`. |

## Inputs and Outputs
Refer to function signatures above for inputs and outputs.

## Redis Keys
None

## Dependencies
- __future__
- base64
- cv2
- numpy
- typing
