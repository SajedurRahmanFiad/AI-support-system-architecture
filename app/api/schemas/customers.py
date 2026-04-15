from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class CustomerOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    brand_id: int
    external_id: str
    display_name: str | None
    language: str | None
    city: str | None
    profile_json: dict[str, Any] | None
    short_summary: str | None
    last_seen_at: datetime | None
    created_at: datetime
    updated_at: datetime


class CustomerFactOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    fact_key: str
    fact_value: str
    confidence: float
    source: str
    created_at: datetime
