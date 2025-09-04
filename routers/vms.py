"""Visitor management router bundling entry and gatepass submodules."""

from __future__ import annotations

from difflib import SequenceMatcher

from fastapi import APIRouter

from . import entry, gatepass

router = APIRouter()
router.include_router(entry.router)
router.include_router(gatepass.router)


# init_context routine
def init_context(cfg_obj: dict, redis_client, templates_path: str) -> None:
    """Initialize context for submodules."""
    entry.init_context(cfg_obj, redis_client, templates_path)
    gatepass.init_context(cfg_obj, redis_client, templates_path)


# expose common functions for backward compatibility
vms_page = entry.vms_page
register_visitor = entry.register_visitor
export_vms = entry.export_vms
vms_stats = entry.vms_stats
gatepass_print = gatepass.gatepass_print

# Expose stats endpoint for dashboards
router.add_api_route("/vms/stats", entry.vms_stats, methods=["GET"])


@router.get("/api/suggest")
async def suggest_names(q: str = "", field: str = "host") -> list[str]:
    """Return fuzzy-matched host or visitor names for autocomplete."""
    if not entry.config_obj.get("features", {}).get("visitor_mgmt"):
        return []
    query = (q or "").lower()
    if not query:
        return []
    if field == "host":
        names = [
            (n.decode() if isinstance(n, bytes) else n)
            for n in entry.redis.hkeys("host_master")
        ]
    else:
        names = [
            (n.decode() if isinstance(n, bytes) else n)
            for n in entry.redis.hkeys("visitor:master")
        ]
    scored = [
        (SequenceMatcher(None, query, name.lower()).ratio(), name)
        for name in names
        if query in name.lower()
        or SequenceMatcher(None, query, name.lower()).ratio() > 0.6
    ]
    scored.sort(reverse=True)
    return [name for _, name in scored][:10]
