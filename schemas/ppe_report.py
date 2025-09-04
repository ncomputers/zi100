from __future__ import annotations

"""Pydantic model for PPE report queries."""

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, confloat, field_validator


class PPEReportQuery(BaseModel):
    """Validation model for PPE report query parameters."""

    start: datetime
    end: datetime
    status: List[str] = []
    min_conf: Optional[confloat(ge=0, le=1)] = None
    color: Optional[str] = None

    @field_validator("end")
    @classmethod
    def check_range(cls, v: datetime, info):
        start = info.data.get("start")
        if start and v < start:
            raise ValueError("end must be after start")
        return v
