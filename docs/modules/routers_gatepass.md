# routers_gatepass
[Back to Architecture Overview](../README.md)

## Purpose
Purpose: Gatepass module.

## Key Classes
None

## Key Functions
- **_cache_gatepass(entry)** - Store gate pass data in Redis using standard keys.
- **_load_gatepass(gate_id)** - Retrieve gate pass data from cache, hash or logs.
- **init_context(cfg_obj, redis_client, templates_path)** - 
- **_save_gatepass(entry)** - 
- **_get_gatepass(gate_id)** - Return gate pass using cache with fallback to Redis hash.

## Inputs and Outputs
Refer to function signatures above for inputs and outputs.

## Redis Keys
- `gatepass:cache:`
- `gatepass:signature:`
- `visits:phone:`

## Dependencies
- __future__
- base64
- config
- cv2
- datetime
- fastapi
- fastapi.responses
- fastapi.templating
- hmac
- json
- loguru
- modules
- modules.email_utils
- numpy
- os
- routers
- time
- typing
- urllib.parse
- utils.redis
- uuid
