# Redis

Redis acts as the central message bus and datastore.

* Configure the connection via the `redis_url` setting in [config.json](../config.json). The application requires a running Redis instance and aborts startup if it cannot connect.
* Streams store person and PPE events, while hashes track known faces and visitors.
* Known face metadata is persisted exclusively in Redis under keys of the form
  `face:known:<id>` with all IDs stored in the `face:known_ids` set.
* Visitor lookups use the `visitor:face_ids` hash mapping gate-pass or visitor IDs
  to their corresponding face IDs.
