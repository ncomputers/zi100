from __future__ import annotations

"""Pydantic models for report queries."""

from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, BeforeValidator, conint, field_validator


class ReportQuery(BaseModel):
    """Validation model for report query parameters."""

    start: datetime
    end: datetime
    type: Literal["person", "vehicle", "face"] = "person"
    view: Literal["graph", "table"] = "graph"
    rows: conint(gt=0, le=200) = 50
    cam_id: Annotated[int | None, BeforeValidator(lambda v: None if v == "" else v)] = (
        None
    )
    label: Annotated[str | None, BeforeValidator(lambda v: None if v == "" else v)] = (
        None
    )
    cursor: int = 0

    @field_validator("end")
    @classmethod
    def check_range(cls, v: datetime, info):
        start = info.data.get("start")
        if start and v < start:
            raise ValueError("end must be after start")
        return v
