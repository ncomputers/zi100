# routers_reports
[Back to Architecture Overview](../README.md)

## Purpose
Count report routes.

## Key Classes
None

## Key Functions
- **init_context(config, trackers, redis_client, templates_path, cameras)** - Initialize shared context for report routes.

## Inputs and Outputs
Refer to function signatures above for inputs and outputs.

## Redis Keys
None

## Dependencies
- __future__
- config
- datetime
- fastapi
- fastapi.responses
- fastapi.templating
- json
- loguru
- modules
- modules.utils
- os
- pathlib
- schemas.report
- typing
