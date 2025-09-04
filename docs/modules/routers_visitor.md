# routers_visitor
[Back to Architecture Overview](../README.md)

## Purpose
Visitor management routes.

## Key Classes
None

## Key Functions
- **_save_visitor_master(name, email, phone, visitor_type, company_name, photo_url)** - Persist visitor info and return visitor_id.
- **_save_host_master(host, email)** -
- **get_host_names_cached()** -
- **invalidate_host_cache()** -
- **_load_known_faces()** -
- **_load_unregistered_faces()** -
- **_trim_visitor_logs()** -
- **init_context(cfg, redis_client, templates_path, cameras)** -
- **_search_embeddings(img_bytes, top_n)** - Return top matches for provided image bytes.
- **_update_request(req_id, new_status)** -

## Inputs and Outputs
Refer to function signatures above for inputs and outputs.

## Face ID Format
`face_id` values must contain only letters, numbers, underscores, or hyphens (`^[A-Za-z0-9_-]+$`).

## Redis Keys
- `data:image/jpeg;base64,`
- `face:known:`
- `face:known_ids`
- `face:unregistered:`
- `face:unregistered_ids`
- `face_db:upload`
- `gatepass:*`
- `visitor:master`

## Dependencies
- __future__
- base64
- binascii
- config
- cv2
- datetime
- fastapi
- fastapi.responses
- fastapi.templating
- json
- loguru
- modules
- modules.utils
- numpy
- pathlib
- pydantic
- time
- typing
- utils.redis
- uuid

## Visitor Report Statuses
The visitor report displays all passes except those marked "rejected" or
"cancelled". Passes with statuses such as "Meeting in progress",
"Completed", and "Expired" now appear alongside approved entries in the
report.
