# modules_utils
[Back to Architecture Overview](../README.md)

## Purpose
Purpose: Utils module.

## Key Classes
None

## Key Functions
- **hash_password(password)** - Hash a password using PBKDF2.
- **verify_password(password, hashed)** - Verify a password against a hash.
- **require_roles(request, roles)** - Ensure the session user has one of ``roles`` or redirect to the login page.
- **require_admin(request)** - Dependency wrapper that requires the ``admin`` role.
- **require_viewer(request)** - Allow access to users with ``viewer`` or ``admin`` roles.

## Inputs and Outputs
Refer to function signatures above for inputs and outputs.

## Redis Keys
None

## Dependencies
- __future__
- fastapi
- fastapi.responses
- passlib.hash
- pathlib
- starlette.status
- threading
