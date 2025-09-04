# Architecture Overview

## System Goals and Components
The Crowd Management System provides real-time person counting and PPE detection. It is built around several major components:

- **Web Server** – FastAPI application that serves the dashboard and REST APIs.
- **Workers** – Background tasks such as `PersonTracker` and `PPEWorker` that process camera streams and handle business logic.
- **Redis** – Central datastore and message broker used for events, metrics, and queues.
- **Models** – YOLO models for person and PPE detection loaded through the model registry.

## Data Flow
```
Camera Streams --> PersonTracker --> Redis --> Dashboard
```
1. Cameras stream frames via GStreamer or FFmpeg.
2. `PersonTracker` analyzes frames and writes events to Redis streams.
3. Background workers consume those streams for PPE checks.
4. The web dashboard subscribes to Redis to display live counts and alerts.

### Capture Pipeline
FFmpeg is the default backend and executes:

```bash
ffmpeg -rtsp_transport tcp -i {url} -f rawvideo -pix_fmt bgr24 -
```

`rtsp_transport` may be set to `udp`, while `ffmpeg_flags` appends custom options. The global `frame_skip` parameter drops frames before analysis to reduce load.

## Deployment Diagram
```
+-----------+       HTTP       +------------+
| Dashboard | <--------------> | Web Server |
+-----------+                  +------------+
                                   |
                        Redis streams & queues
                                   |
                         +------------------+
                          |    Workers       |
                          | (PersonTracker,  |
                          |       PPE)       |
                         +------------------+
```

### Environment Requirements
- Python 3.10+
- Redis server (a running instance is required; fakeredis is not bundled)
- `ffmpeg` command-line tools
- Installed Python dependencies from `requirements.txt` (including `ultralytics`)
- Optional GPU with CUDA for accelerated inference

## Module Documentation
- [Web Server](web-server.md)
- [Workers](workers.md)
- [Redis](redis.md)
- [Models](models.md)

## Getting Started
1. Clone the repository and install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
2. Ensure a Redis instance is running and configured in `config.json`.
3. Start the application:
   ```bash
   uvicorn app:app
   ```
   For HTTPS, pass `--ssl-certfile` and `--ssl-keyfile` or run behind a reverse proxy.
4. Run the test suite to verify your environment:
   ```bash
   python3 -m pytest -q
   ```
5. See [CONTRIBUTING.md](../CONTRIBUTING.md) for development guidelines.
