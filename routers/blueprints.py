"""Helper to initialize and register all router modules."""

from __future__ import annotations

from fastapi import FastAPI

from . import alerts, api_alerts, api_identities, auth
from . import cameras as cam_routes
from . import config_api, dashboard, detections, feedback, health
from . import help as help_pages
from . import mcp, ppe_reports, profile, reports, rtsp, settings
from .admin import users as admin_users

# Ordered registry of router modules
MODULES = [
    dashboard,
    settings,
    cam_routes,
    reports,
    ppe_reports,
    alerts,
    auth,
    admin_users,
    api_alerts,
    api_identities,
    health,
    profile,
    feedback,
    help_pages,
    mcp,
    config_api,
    detections,
    rtsp,
]


# Prepare shared context for each router
# init_all routine
def init_all(
    cfg: dict,
    trackers,
    cams,
    redis_client,
    templates_dir: str,
    config_path: str,
    branding_path: str,
) -> None:
    """Initialize shared context for all routers."""
    settings.init_context(
        cfg, trackers, cams, redis_client, templates_dir, config_path, branding_path
    )
    cam_routes.init_context(cfg, cams, trackers, redis_client, templates_dir)
    reports.init_context(cfg, trackers, redis_client, templates_dir, cams)
    ppe_reports.init_context(cfg, trackers, redis_client, templates_dir)
    api_identities.init_context(cfg, redis_client)

    profile.init_context(cfg, redis_client, templates_dir)
    help_pages.init_context(cfg, templates_dir)
    mcp.init_context(cfg, templates_dir)


# Attach initialized routers to the app
# register_blueprints routine
def register_blueprints(app: FastAPI) -> None:
    """Attach all routers to the given FastAPI app."""
    for mod in MODULES:
        app.include_router(mod.router)
