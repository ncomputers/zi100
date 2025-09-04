# modules_alerts
[Back to Architecture Overview](../README.md)

## Purpose
Purpose: Alerts module.

## Key Classes
- **AlertWorker** - 

## Key Functions
None

## Inputs and Outputs
Refer to function signatures above for inputs and outputs.

Supported alert metrics include PPE anomaly statuses and any event names
listed in `core/events.py` such as `ppe_violation` or
`visitor_registered`.

## Redis Keys
None

## Dependencies
- __future__
- datetime
- io
- json
- loguru
- modules.profiler
- openpyxl
- openpyxl.drawing.image
- pathlib
- threading
- time
- utils
