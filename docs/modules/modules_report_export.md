# modules_report_export
[Back to Architecture Overview](../README.md)

## Purpose
Helpers for exporting PPE reports.

## Key Classes
None

## Key Functions
- **build_ppe_workbook(rows)** - Create a workbook for PPE report rows.  Each row should contain keys: ``time``, ``cam_id``, ``track_id``, ``status``, ``conf``, ``color`` and optional ``image`` pointing to an image file relative to the project root.

## Inputs and Outputs
Refer to function signatures above for inputs and outputs.

## Redis Keys
None

## Dependencies
- __future__
- openpyxl
- openpyxl.drawing.image
- os
- pathlib
- typing
