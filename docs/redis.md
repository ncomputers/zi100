# Redis

Redis acts as the central message bus and datastore.

* Configure the connection via the `redis_url` setting in [config.json](../config.json). The application requires a running Redis instance and aborts startup if it cannot connect.
* Streams store person and PPE events.
