from __future__ import annotations

"""Pydantic models for alert configuration."""
from typing import ClassVar, List, Literal, Optional

from pydantic import BaseModel, EmailStr, conint, field_validator


class EmailConfig(BaseModel):
    """Email configuration options."""

    smtp_host: Optional[str] = None
    smtp_port: Optional[int] = None
    smtp_user: Optional[str] = None
    smtp_pass: Optional[str] = None
    use_tls: Optional[bool] = None
    use_ssl: Optional[bool] = None
    from_addr: Optional[EmailStr] = None


class AlertRule(BaseModel):
    """Validation model for individual alert rules."""

    metric: str
    type: Literal["event", "threshold", "frequency"] = "event"
    value: conint(gt=0)
    recipients: List[EmailStr]
    attach: bool = True

    # set of allowed metric names, supplied by caller
    allowed_metrics: ClassVar[set[str]] = set()

    @field_validator("recipients", mode="before")
    @classmethod
    def split_recipients(cls, v):
        """Allow comma-separated string or list of emails."""
        if isinstance(v, str):
            emails = [a.strip() for a in v.split(",") if a.strip()]
        elif isinstance(v, list):
            emails = v
        else:
            raise ValueError("recipients must be a list or comma-separated string")
        if not emails:
            raise ValueError("at least one recipient required")
        return emails

    @field_validator("metric")
    @classmethod
    def check_metric(cls, v):
        if cls.allowed_metrics and v not in cls.allowed_metrics:
            raise ValueError(f"invalid metric '{v}'")
        return v
