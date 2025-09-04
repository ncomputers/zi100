# modules_gatepass_service
[Back to Architecture Overview](../README.md)

## Purpose
Purpose: Gatepass service helpers.

## Key Classes
None

## Key Functions
- **init(redis_client)** - Initialize redis client for gatepass helpers.
- **build_qr_link(gate_id, request)** - Return absolute URL to view gate pass for QR code generation.
- **render_gatepass_card(rec, qr_image=None)** - Return HTML for gate pass card.
- **update_status(gate_id, status)** - Update status of a gate pass and persist to redis.
- **save_signature(gate_id, data)** - Save base64 signature image and update record.

## Inputs and Outputs
Refer to function signatures above for inputs and outputs.

## Redis Keys
None

## Dependencies
- __future__
- base64
- config
- json
- pathlib
- redis
- typing
- utils.redis
