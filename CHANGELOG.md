# Changelog
- remove automatic local camera discovery
- fix /vms 500 error; add regression tests
- wait for camera metadata before enabling capture buttons
- improve captured image quality and error handling in face search (70% JPEG)
- auto-detect stream type from URLs in tracker and camera factory
- enable FFmpeg HTTP reconnection flags with configurable delay
- document camera API fields and provide curl example
- remove legacy `/manage_faces/*` endpoints; use `GET /api/faces` for listings

