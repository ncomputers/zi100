# modules_visitor_db
[Back to Architecture Overview](../README.md)

## Purpose
Simple Redis helper for frequent visitors and hosts.

## Key Classes
None

## Key Functions
- **init_db(redis_client)** - Initialize Redis client for visitor storage.
- **save_visitor(name, phone, email, org, photo, visitor_id)** - Save visitor info and return a persistent visitor_id.
- **save_host(name, email, dept, location)** - 
- **_decode_map(data)** - 
- **get_or_create_visitor(name, phone, email, org, photo)** - Return existing visitor_id by phone or create a new record.
- **get_visitor_by_phone(phone)** - 
- **get_host(name)** - 
- **search_visitors_by_name(prefix, limit)** - Return visitors whose names start with prefix.

## Inputs and Outputs
Refer to function signatures above for inputs and outputs.

## Redis Keys
- `visitor:host:`
- `visitor:master`
- `visitor:record:`

## Dependencies
- __future__
- json
- loguru
- redis
- typing
- uuid
