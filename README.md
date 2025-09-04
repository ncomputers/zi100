# Crowd Management System v81

Version 81 separates the person counting and PPE detection logic into two
independent modules. The basic **PersonTracker** detects and tracks people and
logs entry/exit events to `person_logs`, pushing items needing PPE checks to
`ppe_queue`. A new **PPEDetector** reads from this queue and stores the results
in `ppe_logs`. Older
entries are pruned automatically based on the configurable
`ppe_log_retention_secs` window. Camera configuration now uses grouped tasks for
counting and PPE detection.

The tracker keeps a complete history of entry and exit events in the
`person_logs` sorted set so the reports API can reconstruct occupancy over
time. When PPE detection is enabled, each relevant `person_logs` entry is copied
to a dedicated PPE queue. The `PPEWorker` consumes that queue and writes results
to `ppe_logs`, ensuring that PPE processing never removes data needed for
standard person-count reports.

Duplicate frame removal and all other features from the previous release are
still available.

## Upgrade Notes

Existing deployments may have camera records without the `show` flag used to
toggle visibility on the dashboard. On startup, the application now adds
`"show": true` to any camera missing this field and saves the update back to
Redis. After upgrading, review the Cameras page to confirm that each camera is
visible as expected.

Camera metadata now resides entirely in Redis, so no database migrations are
required for upgrades or fresh installs.

## Features

- **Multiple camera sources**: Add HTTP or RTSP cameras via the settings page.
- **Person counting and PPE checks**: YOLOv8 is used for person detection and, when enabled, for verifying required PPE.
- **Counting and alerts**: Tracks entries/exits and can send email alerts based on customizable rules.
- **Duplicate frame filter**: Skips nearly identical frames to reduce GPU/CPU load.
- **Dashboard and reports**: Live counts, recent anomalies, and historical reports are available in the web interface.
- **Dashboard polling**: The dashboard refreshes counts by polling `/api/stats` every 2 seconds.
- **Dashboard history API**: Aggregated metrics are available via `/api/dashboard/stats?range=7d` where `range` may be `today`, `7d`, or `this_month`.
- **Debug stats**: Visit `/debug` to monitor raw SSE data, connection status, and camera backend info.
- **Debug overlays**: Toggle line, ID, and count overlays from the Settings page.
- **Live feed optimization**: Dashboard streams the raw camera feed via `/stream/clean/{cam_id}` while analysis runs separately.
- **Per-camera resolution**: Choose 480p, 720p, 1080p, or original when adding a camera.
- **Camera status**: Online/offline indicators appear in the Cameras page for quick troubleshooting.
- **Secure logins**: User passwords are stored as PBKDF2 hashes and verified using passlib.
- **Rotating log file**: `app.log` captures runtime logs with automatic rotation.
- **Historical reports**: A background task records per-minute counts to Redis so
  the reports page can graph occupancy over time. Log entries are stored in Redis
  sorted sets for efficient range queries.
- **Redis stream debug**: Stats are also written to `stats_stream` for reliable debugging.
- **Visitor management**: Unknown faces are queued and can be reviewed and labeled through the Face DB page.
- **Pre-registration & approval**: Hosts can pre-register visitors, approve or reject requests, and receive email notifications.
- **Gatepass creation**: Register visitors with a gatepass ID and print passes with your company logo.
- **Gatepass expiry**: Specify a validity period when creating passes so they automatically expire.
- **Printable gate pass**: Each pass can be opened via `/gatepass/print/{id}` and saved as PDF using html2pdf.js.
- **Multi-format exports**: Visitor and gate pass logs can be downloaded as CSV, XLSX (with photos) or PDF.
- **SaaS-style VMS dashboard**: `/vms` shows occupancy widgets and charts built from `/api/vms/stats`.
- **Dashboard timeframe filter**: Choose Today, Last 7 Days, Last 30 Days, This Month or Year for stats.
- **Face Search**: Upload or capture a face image within the **Face DB** page to search stored visitors.
- **Face DB redesign**: Faces display in a responsive card grid with an optional search toggle.
- **Captured face thumbnails**: Unknown faces are saved with their thumbnails so the Face DB lists them for later review.
- **Validated snapshots**: Frames are queued only when a human face is detected with sufficient clarity and size, preventing junk data.

- **Redis hash storage**: Known and unregistered faces are stored as hashes for efficient access.
- **Face embeddings**: Each face record saves an `embedding` vector for similarity searches.
- **Phone lookup**: Enter a phone number to auto-fill visitor details and reuse the same `visitor_id` for history.
- **Visitor invitations**: Generate appointment links with expiry so guests can self-fill details.
- **Invite page**: Create invites and view pending invitations with quick links.
- **Custom visitor/host reports**: Summaries can be exported as CSV.
- **Printable gate pass**: Includes phone/email and signature boxes, with one-click PDF export.
- **Visit request export**: Download requests filtered by status.
- **Smart suggestions**: Forms auto-complete frequent visitor and host info.
- **Export module**: CSV and Excel exports share a common implementation for reports and logs.
- **Collapsible email settings**: The Email & Alerts page hides SMTP fields until you click **Configure Email**. Alert rules now include visitor registration events.
- **Branding → Company Logo now updates live; if you still see the old image, clear browser cache.**
- **Adding faces via Gate-Pass or Camera**: uploaded photos immediately update the face database and live camera modal.
- **Visitor dashboard revamp**: animated KPI cards and auto-refreshing charts provide a livelier overview.
- **GStreamer streaming**: RTSP cameras use GPU decoding via `nvh264dec` and a leaky queue to drop stale frames for low latency.

## Camera API

Fields accepted by the camera creation endpoint:

- `name`
- `url`
- `orientation`
- `transport`
- `resolution`
- `ppe`
- `vms`
- `face_recog`
- `inout_count`
- `reverse`
- `show`
- `enabled`
- `line`
- `profile`
- `site_id`

Example:

```bash
curl -X POST http://localhost:8000/cameras \
  -H "Content-Type: application/json" \
  -d '{"name":"Gate","url":"rtsp://cam/stream","orientation":"normal","transport":"tcp","resolution":"original","enabled":true}'
```

## Faces API

`GET /api/faces` returns paginated face records.

### Query Parameters

- `status` – one of `known`, `unregistered`, `pending`, or `deleted` (default `known`).
- `q` – optional substring match on the face name.
- `from`, `to` – ISO 8601 datetimes to bound `last_seen_at`.
- `camera_ids` – repeatable camera ID filter.
- `sort` – `last_seen_desc` (default), `last_seen_asc`, `first_seen_asc`,
  `first_seen_desc`, `name_asc`, or `name_desc`.
- `limit` – results per page (1–100, default 20).
- `cursor` – opaque token for cursor-based pagination.

### Cursor Pagination

Responses include `next_cursor` and `prev_cursor`. Pass either value to the
`cursor` parameter to navigate forward or backward.

### Example

```bash
curl 'http://localhost:8000/api/faces?status=known&limit=2'
```

```json
{
  "faces": [
    {
      "id": "abc123",
      "name": "Jane Doe",
      "thumbnail_url": "/faces/abc123.jpg",
      "last_seen_at": 1700000000,
      "first_seen_at": 1699990000,
      "camera": { "id": "1", "label": "Lobby" },
      "status": "known"
    }
  ],
  "counts": {
    "known_count": 1,
    "unregistered_count": 0,
    "pending_count": 0,
    "deleted_count": 0
  },
  "total_estimate": 1,
  "next_cursor": "eyJ2IjoxfQ",
  "prev_cursor": null
}
```

## Face DB UI

The Face DB page provides a filter bar with:

- search, date range, and camera filters
- sorting by last or first seen time or by name
- page size choices of 20, 50, or 100 results

Accessible labels and live region updates ensure screen reader support.

## Invite Lifecycle

1. **Link generation** – a host creates an invite link. The system saves a placeholder record with status `link` along with the host and timestamp. Optional `expiry` or `purpose` fields are stored if supplied.
2. **Visitor submission** – the visitor opens the link and submits their details. The invite becomes `created` and a visit request with status `pending` is queued for host action.
3. **Approval** – the host approves or rejects the request, transitioning the invite to `approved` or `rejected`.

## Installation

1. Install Python 3.10+, Redis, and the `ffmpeg` command-line tools. Redis must be running and reachable; the application exits on startup if it cannot connect.
2. Install dependencies (including `ultralytics`):
   ```bash
   pip install -r requirements.txt
   ```
   For systems with a display, install `opencv-python` to enable OpenCV's GUI
   features. Headless deployments should install `opencv-python-headless` and
   either set `"headless": true` in `config.json` or run without a `DISPLAY`
   environment variable.
3. Install [WeasyPrint](https://weasyprint.org/) and its native dependencies for
   PDF generation. On Debian/Ubuntu:
   ```bash
   sudo apt install libpangocairo-1.0-0 libpangoft2-1.0-0 libcairo2 libgdk-pixbuf2.0-0
   pip install weasyprint
   ```
   The project relies on WeasyPrint—tools like `wkhtmltopdf` are not supported.
4. (Optional) Install GStreamer and its Python bindings if you plan to enable
   GStreamer streaming:
   ```bash
   sudo apt install python3-gi gstreamer1.0-plugins-base \
       gstreamer1.0-plugins-good gstreamer1.0-plugins-bad \
       gstreamer1.0-plugins-ugly gstreamer1.0-tools
   ```
5. (Optional) Install PHP if you want to use the sample PHP pages in `public/`.

## Configuration

Edit `config.json` to set camera URLs, model paths, thresholds, and email settings. Most options can also be adjusted in the web UI under **Settings**. Key fields include:

- `stream_url` – Optional default stream used when launching via the command line.
- `person_model`, `ppe_model` – Paths to YOLO models.
- `device` – `auto`, `cpu`, or `cuda:0`. `auto` uses GPU if available,
  otherwise falls back to CPU with a warning.
- `headless` – Set to `true` to force offscreen mode when no display is
  available.
- `max_capacity` and `warn_threshold` – Occupancy limits.
- `redis_url` – Location of the Redis instance (required). The server must be reachable at startup or the application will terminate.
- `email` – SMTP configuration. Set `smtp_host`, `smtp_port`, `smtp_user`, `smtp_pass`, `use_tls`/`use_ssl`, and `from_addr` to enable email alerts.
- `default_host` – Optional host name used when no host is provided. When set,
  the visitor form pre-fills this value and host validation is skipped.
- `stream_mode` – Maintained for backward compatibility; FFmpeg is tried first
  and GStreamer is used only if initialization fails.
- `enable_gstreamer` – Set to `true` (default) to load GStreamer bindings. The
  app automatically disables this flag if `gst-launch-1.0` is missing or fails
  to run. When `false` the application skips `gi` imports and relies on
  FFmpeg/OpenCV.
- `backend_priority` – Ordered list of capture backends to try (default
  `["ffmpeg", "gstreamer", "opencv"]`). Disabled backends are skipped
  automatically. `opencv` is only attempted when a live dashboard view is
  requested (`for_display=True`); otherwise it is removed.
- `pipeline_profiles` – Named capture settings. See
  [camera factory examples](docs/modules/modules_camera_factory.md#full-pipeline-profiles)
  for GStreamer, FFmpeg and OpenCV profiles with equivalent command-line
  pipelines.
- `capture_buffer_seconds` – Length of encoded video to buffer before dropping (5–60).
- `frame_skip` – Number of frames to skip between processed frames (default 3).
- `detector_fps` – Maximum detector invocations per second (default 10).
- `adaptive_skip` – Enable motion-based frame skipping when `true`.
- `ffmpeg_flags` – Extra FFmpeg options appended to the capture command (default `"-flags low_delay -fflags nobuffer"`).
- `cpu_limit_percent` – Percent of CPU cores allocated to processing. The
  resolved core count sets process CPU affinity and caps threads in BLAS-backed
  libraries (default 50).
- `show_counts` – Display "Entering"/"Exiting" labels on the live feed when enabled.
- `license_key` – JWT license token controlling maximum cameras and feature access.
- `ppe_log_retention_secs` – Seconds to retain PPE log entries before they are pruned (default 604800).
- `duplicate_bypass_seconds` – Cooldown window in seconds to skip repeated PPE statuses for the same track (default 2).
- `track_objects` – YOLO labels or alias names to track. Aliases such as `"vehicle"`
  expand to multiple classes (`car`, `truck`, `bus`, `motorcycle`, etc.).

### Entry/exit logging with PPE detection

Enabling counting and PPE checks together requires both features in
`config.json` and camera tasks that include the desired PPE classes. The
`person_logs` history remains intact because the PPE worker consumes entries from
its own queue.

```json
{
  "features": {
    "in_out_counting": true,
    "ppe_detection": true
  },
  "track_ppe": ["helmet"],
  "cameras": [
    {
      "id": "gate1",
      "url": "rtsp://user:pass@cam/stream",
      "tasks": ["in_count", "out_count", "helmet", "no_helmet"]
    }
  ]
}
```

### FFmpeg pipeline

The default camera backend invokes:

```bash
ffmpeg -rtsp_transport tcp -i {url} -f rawvideo -pix_fmt bgr24 -
```

Key options:

- `frame_skip` – Drop frames between analyses to reduce load.
- `detector_fps` – Limit how often the detector runs.
- `adaptive_skip` – Increase/decrease `frame_skip` based on motion.
- `rtsp_transport` – `tcp` (default) or `udp` for the RTSP transport.
- `ffmpeg_flags` – Extra arguments appended to the command.

Example `config.json`:

```json
{
  "frame_skip": 0,
  "pipeline_profiles": {
    "default": {
      "backend": "ffmpeg",
      "ffmpeg_flags": "-rtsp_transport tcp"
    }
  },
  "cameras": [
    { "id": "lobby", "url": "rtsp://user:pass@cam/stream" },
    {
      "id": "dock",
      "url": "rtsp://user:pass@cam2/stream",
      "ffmpeg_flags": "-rtsp_transport udp"
    }
  ]
}
```

The first camera uses the default pipeline, while the second overrides the transport.

#### Troubleshooting FFmpeg

- **Authentication errors (401/403)** – verify the username and password.
- **Network issues** – `No route to host` or timeouts suggest connectivity problems; check firewalls and cabling.
- **Short read** – messages like `Connection reset` or `short read` indicate the camera closed the connection; switch transports or lower `frame_skip`.

### Logging

Logging is configured via [`logging_config.py`](logging_config.py) using Loguru with JSON output and rotation. Adjust verbosity by setting the `LOG_LEVEL` environment variable (e.g., `LOG_LEVEL=DEBUG`) or by adding a `log_level` entry in `config.json`.

## Licensing

The application verifies the `license_key` on startup but will still run if the token is missing or invalid. Feature limits remain disabled until a valid key is activated. Use the **Settings** page (or `/license` endpoint) to update the key at runtime. The page shows license details such as client name, enabled features and expiration. Administrators can generate keys with `key_gen.py` or `license_generator.py`, enabling optional modules like PPE Detection, Visitor Management and Face Recognition.

## Running

Launch the FastAPI application:

```bash
python3 app.py
```

Then open `http://localhost:5002` in your browser. Use the **Cameras** page to add streams (HTTP, RTSP or local webcams) and **Settings** to adjust options. Tests can be executed with `pytest`:

```bash
python3 -m pytest -q tests
```

> **Note:** Features that access the webcam via `getUserMedia` require HTTPS. Run the
> server with TLS by setting `SSL_CERTFILE` and `SSL_KEYFILE` or deploy behind an
> HTTPS‑enabled reverse proxy.

### Display modes

The server supports both GUI and headless deployments:

- **GUI mode** – Requires a display and the `opencv-python` package. Ensure
  `"headless": false` in `config.json`.
- **Headless mode** – Set `"headless": true` or run without a `DISPLAY`
  variable. The application sets `QT_QPA_PLATFORM=offscreen` and requires
  `opencv-python-headless`.
  In headless mode, the application skips the OpenCV backend unless a client
  opens the dashboard's live view and `for_display` is explicitly enabled.

### Choosing capture_buffer_seconds

The capture buffer holds encoded video data so that temporary inference delays
don't interrupt streaming. Set a higher value (up to 60&nbsp;s) for unstable
networks, or lower for minimal latency. Worst-case latency is roughly
`capture_buffer_seconds / FPS`.

## Directory Structure

- `app.py` – FastAPI entry point.
- `core/` – Helper modules such as configuration and tracker manager.
- `modules/` – Tracking, alerts, and utilities.
- `routers/` – API routes for dashboard, settings, reports, and cameras.
- `templates/` – HTML templates rendered by FastAPI.
- `public/` – Optional PHP pages.
- `tests/` – Simple unit tests.

## Visitor Management

When the `visitor_mgmt` feature is licensed, the navigation bar includes a
**VMS** link. This link is hidden if the feature is disabled. The VMS page
provides visitor registration with optional photo capture and shows recent
visitors. Records are stored in Redis and can be exported as CSV. Known faces
can still be managed separately on the **Face DB** page.

### Configuration

- `features.visitor_mgmt` – Enable the visitor management interface and
  invitation workflows; must be licensed and set to `true` to expose VMS
  navigation links.
- `face_match_thresh` – Recognition threshold for matching faces (0–1, default 0.6)
- `visitor_conf_thresh` – Minimum detection confidence
- `visitor_sim_thresh` – Embedding similarity for merging
- `visitor_min_face_size` – Skip faces below this size
- `visitor_blur_thresh` – Blur cutoff for saving a face
- `visitor_size_thresh` – Minimum bounding box area
- `visitor_fps_skip` – Frame skip value for processing

### Invite links

Visitor invite creation is available only when `features.visitor_mgmt` is enabled in the configuration. Set `base_url` to the externally accessible address so that generated links are absolute. If `base_url` is omitted, the service falls back to the request URL and scheme.

### Face Recognition

Visitor photos from gate passes, invites and the camera modal are processed with
the `buffalo_l` model. When a single face is detected the embedding is saved in
Redis under `face_db` and appended to an in-memory FAISS index that is
reconstructed from Redis on startup. Similarity search is exposed via
`/api/faces/search` which returns the top matches and cosine scores. A score of
`0.4` or greater is typically considered a strong match.

#### FAISS Index Maintenance

The FAISS index mirrors embeddings stored in Redis. `id_map` ordering is
persisted in the `face:id_map` list and the index is rebuilt automatically on
startup. If the index becomes corrupted or desynchronized, clear the list and
reinitialize:

```python
from modules import face_db
from config import config
import redis

r = redis.Redis()  # configure as needed
r.delete('face:id_map')
face_db.init(config, r)
```

Restarting the service will load the regenerated index.

## Development Tips

This repository uses a `.gitattributes` file that keeps incoming changes during merges.
If merge conflicts occur, Git will prefer the incoming version.

## Redis Key Naming

Redis keys follow a colon-separated scheme of `<module>:<entity>:<id>` to avoid collisions.
Collections without a specific identifier may omit the final segment
(e.g., `visitor:master`). Additional segments may be appended for attributes.

Examples:

- `person_tracker:cam:1:in` – entry count for camera `1`.
- `visitor:master` – hash of visitor names to contact info.
- `visitor:record:5551234` – visitor details keyed by phone number.
- `visitor:host:alice` – host information.

Use this pattern for any new Redis keys to keep the namespace consistent.

## File Reference

The repository contains the following files:

### Root files

- `app.py` – main FastAPI application.
- `config.py` – shared configuration dictionary.
- `config.json` – example configuration used at startup.
- `key_gen.py` – interactive license token generator.
- `license_generator.py` – command line generator for licenses.
- `license_plate_detector.pt` – pretrained model for license plates.
- `requirements.txt` – Python dependency list.
- `__init__.py` – marks the project package.
- `README.md` – this documentation file.

### Admin

- `Admin/license_generator.py` – interactive generator built with Authlib.

### core

- `core/__init__.py` – package marker for core modules.
- `core/config.py` – load, save and normalize configuration.
- `core/stats.py` – aggregate statistics and publish to Redis.
- `core/tracker_manager.py` – start and manage `PersonTracker` instances.

### modules

- `modules/__init__.py` – package initialization.
- `modules/alerts.py` – background email alert worker.
- `modules/camera_factory.py` – helpers for opening camera streams.
- `modules/duplicate_filter.py` – drop nearly identical frames.
- `modules/ffmpeg_stream.py` – FFmpeg based camera wrapper.
- `modules/gstreamer_stream.py` – GStreamer camera wrapper.
- `modules/license.py` – license token utilities.
- `modules/overlay.py` – draw tracking overlays on frames.
- `modules/tracker/manager.py` – main tracking and counting logic.
- `modules/ppe_worker.py` – process person logs for PPE detection.
- `modules/profiler.py` – lightweight profiling utilities.
- `modules/utils.py` – misc helpers (password hashing, email, etc.).
- `workers/visitor/__init__.py` – visitor face recognition worker.
- `modules/export.py` – helper functions for CSV, Excel and PDF exports.
- `modules/visitor_db.py` – Redis storage for frequent visitors and hosts.

### routers

- `routers/__init__.py` – package marker.
- `routers/alerts.py` – routes for alert rules and email tests.
- `routers/auth.py` – login and logout endpoints.
- `routers/cameras.py` – camera CRUD and preview routes.
- `routers/dashboard.py` – dashboard pages and streaming APIs.
- `routers/ppe_reports.py` – PPE report generation endpoints.
- `routers/reports.py` – person/vehicle report APIs.
- `routers/settings.py` – update and export configuration.
- `routers/visitor.py` – visitor management HTTP endpoints.
- `routers/vms.py` – blueprint that includes the VMS entry and gate pass routers.
- `routers/entry.py` – routes for visitor entries and exports.
- `routers/gatepass.py` – route for printing gate passes.

### templates

- `templates/*.html` – Jinja2 templates for the web UI.
- `templates/partials/header.html` and `footer.html` – shared layout pieces.
- `templates/face_search.html` – standalone template used for the Face DB search form.
- `templates/appointment.html` – visitor self-fill appointment form.
- `templates/gatepass_print.html` – printable gate pass used by `/gatepass/print/{id}`.

### static

- `static/css/flatpickr.min.css` – bundled CSS for date pickers.
- `static/js/chart.min.js` – chart rendering library.
- `static/js/flatpickr.min.js` – date picker library.
- `static/logo1.png` and `static/logo2.png` – sample logos.

### public

- `public/dashboard.php` – PHP example dashboard.
- `public/report.php` – PHP report page.

### tests

- `tests/test_license.py` – verify license helpers.
- `tests/test_ffmpeg_stream.py` – test FFmpeg stream wrapper.
- `tests/test_ppe_worker.py` – test PPE worker logic.
- `tests/test_reports.py` – test reporting endpoints.
- `tests/test_alerts.py` – test email alerts and metrics.
- `tests/test_visitor_worker.py` – test visitor worker functions.
- `tests/test_visitors.py` – test visitor routes.
- `tests/test_vms.py` – test VMS endpoints.
- `tests/TEST.PY` – simple FFmpeg stream example.

### Low-latency capture

The camera wrappers keep only the latest **N** frames in memory. A larger buffer
adds roughly `N / FPS` of latency but smooths out short processing spikes. Set
`capture_buffer` in `config.json` (default `3`). For 60&nbsp;fps sports feeds try
`5`, while low frame rate CCTV works well with `2`. Local USB cameras default to
`local_buffer_size=1` for minimal delay; increase it if you experience dropped
frames during processing spikes.

The factory verifies that a stream is delivering frames and will automatically
fall back from GStreamer to FFmpeg (or OpenCV) if needed.

Benchmark with:

```bash
gst-launch-1.0 rtspsrc location=... ! videorate drop-only=true ! fpsdisplaysink text-overlay=false
ffplay -flags low_delay -fflags nobuffer -i rtsp://...
python -m modules.latency_probe --url rtsp://... --buffer 3
```

## Package Documentation

Detailed documentation for internal modules and routers is available below.

### Modules

- [**init**](docs/modules/modules___init__.md)
- [alerts](docs/modules/modules_alerts.md)
- [base_camera](docs/modules/modules_base_camera.md)
- [camera_factory](docs/modules/modules_camera_factory.md)
- [capture_utils](docs/modules/modules_capture_utils.md)
- [duplicate_filter](docs/modules/modules_duplicate_filter.md)
- [email_utils](docs/modules/modules_email_utils.md)
- [export](docs/modules/modules_export.md)
- [face_db](docs/modules/modules_face_db.md)
- [face_engine**\_init**](docs/modules/modules_face_engine___init__.md)
- [face_engine_detector](docs/modules/modules_face_engine_detector.md)
- [face_engine_embedder](docs/modules/modules_face_engine_embedder.md)
- [face_engine_router](docs/modules/modules_face_engine_router.md)
- [face_engine_utils](docs/modules/modules_face_engine_utils.md)
- [ffmpeg_stream](docs/modules/modules_ffmpeg_stream.md)
- [gatepass_service](docs/modules/modules_gatepass_service.md)
- [gstreamer_stream](docs/modules/modules_gstreamer_stream.md)
- [license](docs/modules/modules_license.md)
- [model_registry](docs/modules/modules_model_registry.md)
- [opencv_stream](docs/modules/modules_opencv_stream.md)
- [overlay](docs/modules/modules_overlay.md)
- [person_tracker](docs/modules/modules_person_tracker.md)
- [ppe_worker](docs/modules/modules_ppe_worker.md)
- [profiler](docs/modules/modules_profiler.md)
- [report_export](docs/modules/modules_report_export.md)
- [utils](docs/modules/modules_utils.md)
- [visitor_db](docs/modules/modules_visitor_db.md)
- [visitor_worker](docs/modules/modules_visitor_worker.md)

### Routers

- [**init**](docs/modules/routers___init__.md)
- [alerts](docs/modules/routers_alerts.md)
- [api_faces](docs/modules/routers_api_faces.md)
- [auth](docs/modules/routers_auth.md)
- [blueprints](docs/modules/routers_blueprints.md)
- [cameras](docs/modules/routers_cameras.md)
- [dashboard](docs/modules/routers_dashboard.md)
- [entry](docs/modules/routers_entry.md)
- [gatepass](docs/modules/routers_gatepass.md)
- [ppe_reports](docs/modules/routers_ppe_reports.md)
- [reports](docs/modules/routers_reports.md)
- [settings](docs/modules/routers_settings.md)
- [visitor](docs/modules/routers_visitor.md)
- [vms](docs/modules/routers_vms.md)
