from __future__ import annotations

"""User management routes."""

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.templating import Jinja2Templates

from core.config import save_config
from modules.utils import hash_password, require_admin
from schemas.user import UserCreate, UserUpdate
from utils.deps import get_config_path, get_redis, get_settings, get_templates

# Default roles and modules for user accounts
DEFAULT_ROLES = ["admin", "viewer"]
DEFAULT_MODULES = ["dashboard", "visitors", "reports", "settings"]

router = APIRouter(prefix="/admin", dependencies=[Depends(require_admin)])


def allowed_roles(cfg: dict) -> list[str]:
    """Return permitted user roles from configuration."""
    return cfg.get("roles", DEFAULT_ROLES)


def available_modules(cfg: dict) -> list[str]:
    """Return available modules from configuration."""
    return cfg.get("modules", DEFAULT_MODULES)


@router.get("/users")
async def users_page(
    request: Request,
    cfg: dict = Depends(get_settings),
    templates: Jinja2Templates = Depends(get_templates),
):
    """Render a simple user management page."""
    roles = allowed_roles(cfg)
    modules = available_modules(cfg)
    return templates.TemplateResponse(
        "admin/users.html",
        {
            "request": request,
            "users": cfg.get("users", []),
            "cfg": cfg,
            "roles": roles,
            "modules": modules,
        },
    )


@router.post("/users")
async def create_user(
    user: UserCreate,
    current=Depends(require_admin),
    cfg: dict = Depends(get_settings),
    redis=Depends(get_redis),
    cfg_path: str = Depends(get_config_path),
):
    """Create a new user and persist to config."""
    users = cfg.setdefault("users", [])
    if any(u["username"] == user.username for u in users):
        raise HTTPException(status_code=400, detail="exists")
    roles = allowed_roles(cfg)
    modules = available_modules(cfg)
    if user.role not in roles:
        raise HTTPException(status_code=400, detail="invalid_role")
    if any(m not in modules for m in user.modules):
        raise HTTPException(status_code=400, detail="invalid_module")
    users.append(
        {
            "username": user.username,
            "password": user.password or "",
            "role": user.role,
            "modules": user.modules,
            "email": user.email,
            "name": user.name,
            "phone": user.phone,
            "require_2fa": user.require_2fa,
            "status": "pending",
            "mfa_enabled": user.mfa_enabled,
            "last_login": user.last_login,
            "created_on": datetime.utcnow(),
            "created_by": current.get("name"),

        }
    )
    save_config(cfg, cfg_path, redis)
    return {"created": True}


@router.put("/users/{username}")
async def update_user(
    username: str,
    data: UserUpdate,
    cfg: dict = Depends(get_settings),
    redis=Depends(get_redis),
    cfg_path: str = Depends(get_config_path),
):
    """Update an existing user."""
    users = cfg.get("users", [])
    roles = allowed_roles(cfg)
    modules = available_modules(cfg)
    for u in users:
        if u["username"] == username:
            if data.password is not None:
                u["password"] = hash_password(data.password)
            if data.role is not None:
                if data.role not in roles:
                    raise HTTPException(status_code=400, detail="invalid_role")
                u["role"] = data.role
            if data.modules is not None:
                if any(m not in modules for m in data.modules):
                    raise HTTPException(status_code=400, detail="invalid_module")
                u["modules"] = data.modules
            if data.email is not None:
                u["email"] = data.email
            if data.name is not None:
                u["name"] = data.name
            if data.phone is not None:
                u["phone"] = data.phone
            if data.require_2fa is not None:
                u["require_2fa"] = data.require_2fa
            if data.status is not None:
                u["status"] = data.status
            if data.mfa_enabled is not None:
                u["mfa_enabled"] = data.mfa_enabled
            if data.last_login is not None:
                u["last_login"] = data.last_login

            save_config(cfg, cfg_path, redis)
            return {"updated": True}
    raise HTTPException(status_code=404, detail="not_found")


@router.delete("/users/{username}")
async def delete_user(
    username: str,
    cfg: dict = Depends(get_settings),
    redis=Depends(get_redis),
    cfg_path: str = Depends(get_config_path),
):
    """Remove a user from the configuration."""
    users = cfg.get("users", [])
    for i, u in enumerate(users):
        if u["username"] == username:
            if (
                u.get("role") == "admin"
                and sum(1 for usr in users if usr.get("role") == "admin") == 1
            ):
                raise HTTPException(status_code=400, detail="cannot_delete_last_admin")

            users.pop(i)
            save_config(cfg, cfg_path, redis)
            return {"deleted": True}
    raise HTTPException(status_code=404, detail="not_found")


def _set_status(username: str, status: str, cfg: dict, cfg_path: str, redis) -> dict:
    users = cfg.get("users", [])
    for u in users:
        if u["username"] == username:
            u["status"] = status
            save_config(cfg, cfg_path, redis)
            return {"status": status}
    raise HTTPException(status_code=404, detail="not_found")


@router.post("/users/{username}/enable")
async def enable_user(
    username: str,
    cfg: dict = Depends(get_settings),
    redis=Depends(get_redis),
    cfg_path: str = Depends(get_config_path),
):
    """Enable a user account."""
    return _set_status(username, "active", cfg, cfg_path, redis)


@router.post("/users/{username}/disable")
async def disable_user(
    username: str,
    cfg: dict = Depends(get_settings),
    redis=Depends(get_redis),
    cfg_path: str = Depends(get_config_path),
):
    """Disable a user account."""
    return _set_status(username, "disabled", cfg, cfg_path, redis)


@router.post("/users/{username}/reset-password")
async def reset_password(
    username: str,
    cfg: dict = Depends(get_settings),
    redis=Depends(get_redis),
    cfg_path: str = Depends(get_config_path),
):
    """Reset a user's password."""
    users = cfg.get("users", [])
    for u in users:
        if u["username"] == username:
            u["password"] = ""

            save_config(cfg, cfg_path, redis)
            return {"reset": True}
    raise HTTPException(status_code=404, detail="not_found")


@router.post("/users/{username}/force-logout")
async def force_logout(
    username: str,
    cfg: dict = Depends(get_settings),
    redis=Depends(get_redis),
    cfg_path: str = Depends(get_config_path),
):
    """Force a user to log out by clearing last login."""
    users = cfg.get("users", [])
    for u in users:
        if u["username"] == username:
            u["last_login"] = None
            save_config(cfg, cfg_path, redis)
            return {"logout": True}
    raise HTTPException(status_code=404, detail="not_found")


@router.get("/users/export")
async def export_users(
    cfg: dict = Depends(get_settings),
    redis=Depends(get_redis),
    cfg_path: str = Depends(get_config_path),
):
    """Export user data without passwords."""
    users = cfg.get("users", [])
    data = [{k: v for k, v in u.items() if k != "password"} for u in users]
    save_config(cfg, cfg_path, redis)
    return {"users": data}

