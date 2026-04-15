from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class JobOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    brand_id: int | None
    kind: str
    status: str
    payload_json: dict[str, Any] | None
    result_json: dict[str, Any] | None
    attempts: int
    available_at: datetime | None
    locked_at: datetime | None
    last_error: str | None
    created_at: datetime
    updated_at: datetime


class ProcessJobsRequest(BaseModel):
    limit: int = Field(default=10, ge=1, le=100)
