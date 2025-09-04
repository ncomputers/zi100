# routers_settings
[Back to Architecture Overview](../README.md)

## Purpose
Settings management routes.

Alert and preview settings now use distinct anomaly lists in the template context.

## Key Classes
None

## Key Functions
- **init_context(config, trackers, cameras, redis_client, templates_path, config_path, branding_file)** - Store shared objects for settings routes.

## Inputs and Outputs
Refer to function signatures above for inputs and outputs.

## Redis Keys
None

## Dependencies
- __future__
- config
- core.config
- core.tracker_manager
- datetime
- fastapi
- fastapi.responses
- fastapi.templating
- json
- modules.utils
- pathlib
- time
- typing
- uuid
