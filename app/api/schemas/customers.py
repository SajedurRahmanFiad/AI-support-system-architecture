from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


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


class CustomerUpdate(BaseModel):
    display_name: str | None = None
    language: str | None = None
    city: str | None = None
    profile: dict[str, Any] | None = None
    short_summary: str | None = None


class CustomerFactCreate(BaseModel):
    fact_key: str
    fact_value: str
    confidence: float = Field(default=0.6, ge=0.0, le=1.0)
    source: str = "dashboard"


class CustomerFactUpdate(BaseModel):
    fact_key: str | None = None
    fact_value: str | None = None
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    source: str | None = None
