from __future__ import annotations

"""Pydantic models for gatepass routes."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, field_validator


class GatepassBase(BaseModel):
    """Basic gate pass record."""

    gate_id: str
    name: str
    phone: str
    host: str
    purpose: str
    ts: int
    valid_to: Optional[int] = None
    status: str

    model_config = ConfigDict(extra="allow")


class GatepassCreateResponse(BaseModel):
    """Response model for gate pass creation."""

    saved: bool
    gate_id: str
    time: str
    status: str
    qr: str
    digital_pass_url: str
    approval_url: str | None = None


class GatepassRequiredFields(BaseModel):
    """Fields required for gate pass issuance."""

    phone: str
    purpose: str
    id_proof_type: str

    @field_validator("phone", "purpose", "id_proof_type")
    @classmethod
    def _not_empty(cls, value: str) -> str:
        if not value or not value.strip():
            raise ValueError("must not be empty")
        return value

    model_config = ConfigDict(extra="allow")
