# routers_api_faces
[Back to Architecture Overview](../README.md)

## Purpose
Purpose: Api faces module.

## Key Classes
None

## Key Functions
- **init_context(cfg, redis_client)** - Initialize helper modules.

## GET /api/faces

Fetch paginated face records.

### Parameters

- `status`: `known`, `unregistered`, `pending`, or `deleted` (default `known`).
- `q`: optional substring filter on `name`.
- `from`, `to`: ISO 8601 datetimes to bound `last_seen_at`.
- `camera_ids`: repeatable camera ID filter.
- `sort`: `last_seen_desc`, `last_seen_asc`, `first_seen_asc`, `first_seen_desc`, `name_asc`, or `name_desc`.
- `limit`: results per page (1–100, default 20).
- `cursor`: opaque token for cursor pagination.

### Cursor Usage

Responses include `next_cursor` and `prev_cursor`; supply either value to the
`cursor` parameter to page forward or backward.

### Example Response

```json
{
  "faces": [
    {
      "id": "123",
      "name": "Alice",
      "thumbnail_url": "/faces/123.jpg",
      "last_seen_at": 1700000000,
      "first_seen_at": 1690000000,
      "camera": {"id": "1", "label": "Lobby"},
      "status": "known"
    }
  ],
  "counts": {"known_count": 1, "unregistered_count": 0, "pending_count": 0, "deleted_count": 0},
  "total_estimate": 1,
  "next_cursor": "...",
  "prev_cursor": null
}
```

## Inputs and Outputs
Refer to function signatures above for inputs and outputs.

## Redis Keys
None

## Dependencies
- __future__
- fastapi
- fastapi.responses
- modules
