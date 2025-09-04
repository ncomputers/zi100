CREATE TABLE IF NOT EXISTS cameras (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    type TEXT NOT NULL,
    url TEXT NOT NULL,
    analytics JSON,
    line JSON,
    orientation TEXT NOT NULL,
    transport TEXT NOT NULL,
    resolution TEXT,
    reverse BOOLEAN NOT NULL DEFAULT 0,
    show BOOLEAN NOT NULL DEFAULT 0,
    profile TEXT,
    site_id TEXT,
    enabled BOOLEAN NOT NULL DEFAULT 1,
    created_at DATETIME NOT NULL,
    updated_at DATETIME NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_cameras_site_id_name ON cameras(site_id, name);
