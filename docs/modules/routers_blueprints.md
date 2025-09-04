# routers_blueprints
[Back to Architecture Overview](../README.md)

## Purpose
Helper to initialize and register all router modules.

## Key Classes
None

## Key Functions
- **init_all(cfg, trackers, cams, redis_client, templates_dir, config_path, branding_path)** - Initialize shared context for all routers.
- **register_blueprints(app)** - Attach all routers to the given FastAPI app.

## Inputs and Outputs
Refer to function signatures above for inputs and outputs.

## Redis Keys
None

## Dependencies
- __future__
- fastapi
