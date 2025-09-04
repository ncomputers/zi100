# modules_duplicate_filter
[Back to Architecture Overview](../README.md)

## Purpose
Purpose: Duplicate filter module.

## Key Classes
- **DuplicateFilter** - Detect duplicate frames using perceptual hashing with an optional bypass.

When used with RTSP sources, ``mpdecimate`` in FFmpeg is recommended to drop
duplicates before they reach Python. This filter provides a fallback for
other sources.

## Key Functions
None

## Inputs and Outputs
Refer to function signatures above for inputs and outputs.

## Redis Keys
None

## Dependencies
- PIL
- cv2
- imagehash
- time
