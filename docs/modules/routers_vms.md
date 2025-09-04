# routers_vms
[Back to Architecture Overview](../README.md)

## Purpose
Visitor management router bundling entry and gatepass submodules.

## Key Classes
None

## Key Functions
- **init_context(cfg_obj, redis_client, templates_path)** - Initialize context for submodules.

## Inputs and Outputs
Refer to function signatures above for inputs and outputs.

## Redis Keys
- `visitor:master`

## Dependencies
- __future__
- difflib
- fastapi
