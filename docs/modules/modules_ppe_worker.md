# modules_ppe_worker
[Back to Architecture Overview](../README.md)

## Purpose
Perform PPE detection on snapshots queued from person entry/exit events.
Events names such as `ppe_violation` are defined centrally in
`core/events.py` to ensure consistency.

## Key Classes
- **PPEDetector** - Background worker that pulls entries from the PPE queue,
  loads the saved image, and records results in `ppe_logs`.

## Key Functions
- **determine_status(scores, item, thresh)** - Return (status, conf) based on detection scores.

## Inputs and Outputs
Refer to function signatures above for inputs and outputs.

## Data Flow
- `person_logs` retains all entry/exit events for reporting.
- Events requiring PPE checks are copied to a separate queue
  (`ppe_queue`).
- The `PPEWorker` consumes `ppe_queue` and appends detection outcomes to
  `ppe_logs` without removing data from `person_logs`.
- Progress is tracked via `ppe_worker:last_ts` and counters like
  `ppe_report_version` or per-status counts such as `no_helmet_count`.

## Configuration Example
```json
{
  "features": {
    "in_out_counting": true,
    "ppe_detection": true
  },
  "track_ppe": ["helmet"],
  "alert_rules": [
    {
      "metric": "ppe_violation",
      "type": "event",
      "value": 1,
      "recipients": "safety@example.com"
    }
  ],
  "cameras": [
    {
      "id": "gate1",
      "url": "rtsp://user:pass@cam/stream",
      "tasks": ["in_count", "out_count", "helmet", "no_helmet"]
    }
  ]
}
```

## Redis Keys
- `ppe_queue`
- `ppe_worker:last_ts`
- `ppe_logs`
- `ppe_report_version`
- `no_<item>_count` (e.g., `no_helmet_count`)

### Example `ppe_logs` entry
```json
{
  "ts": 1697040000,
  "cam_id": "gate1",
  "track_id": 42,
  "status": "no_helmet",
  "conf": 0.87,
  "path": "snap123.jpg"
}
```

### Example `events` entry
When the status begins with `"no_"`, the worker also publishes a
`ppe_violation` event for alert rules:

```json
{
  "ts": 1697040000,
  "event": "ppe_violation",
  "cam_id": "gate1",
  "track_id": 42,
  "status": "no_helmet",
  "path": "snap123.jpg"
}
```

## Dependencies
- cv2
- json
- loguru
- modules.profiler
- pathlib
- psutil
- threading
- time
- utils.gpu
- utils.redis
