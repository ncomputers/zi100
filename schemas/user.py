from __future__ import annotations

"""Pydantic models for user management."""

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field


class UserBase(BaseModel):
    email: Optional[str] = None
    name: Optional[str] = None
    phone: Optional[str] = None
    require_2fa: bool = False
    status: str = "pending"
    mfa_enabled: bool = False
    last_login: Optional[datetime] = None
    created_on: Optional[datetime] = None
    created_by: Optional[str] = None
    role: str = "viewer"
    modules: List[str] = Field(default_factory=list)

    mfa_enabled: bool = False


class UserCreate(UserBase):
    username: str
    password: Optional[str] = None


class UserUpdate(BaseModel):
    password: Optional[str] = None
    role: Optional[str] = None
    modules: Optional[List[str]] = None
    email: Optional[str] = None
    name: Optional[str] = None
    phone: Optional[str] = None
    require_2fa: Optional[bool] = None
    status: Optional[str] = None
    mfa_enabled: Optional[bool] = None
    last_login: Optional[datetime] = None

