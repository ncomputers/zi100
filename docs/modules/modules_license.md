# modules_license
[Back to Architecture Overview](../README.md)

## Purpose
License verification and generation helpers without external deps.

## Key Classes
None

## Key Functions
- **_b64encode(data)** - 
- **_b64decode(data)** - 
- **generate_license(secret, days, max_cameras, features, client)** - Create a signed license token using HMAC-SHA256.
- **verify_license(license_key, secret)** - Validate a license token created by :func:`generate_license`.

## Inputs and Outputs
Refer to function signatures above for inputs and outputs.

## Redis Keys
None

## Dependencies
- base64
- datetime
- hashlib
- hmac
- json
- time
