# routers_alerts
[Back to Architecture Overview](../README.md)

## Purpose
Email and alert rule management routes.

## Key Classes
- **CsrfSettings** - 

## Key Functions
- **get_csrf_config()** - Provide CSRF settings using environment or config values.

## Inputs and Outputs
Refer to function signatures above for inputs and outputs.

## Redis Keys
None

## Dependencies
- __future__
- config
- core.config
- fastapi
- fastapi.responses
- fastapi.templating
- fastapi_csrf_protect
- json
- modules.utils
- os
- pydantic
- pydantic_settings
- schemas.alerts
- utils.deps
