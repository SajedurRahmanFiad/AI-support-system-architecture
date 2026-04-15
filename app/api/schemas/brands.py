from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class BrandCreate(BaseModel):
    name: str
    slug: str
    description: str | None = None
    default_language: str = "en"
    tone_name: str = "Helpful sales assistant"
    tone_instructions: str = ""
    fallback_handoff_message: str = "A human teammate will continue this conversation shortly."
    public_reply_guidelines: str | None = None
    settings: dict[str, Any] = Field(default_factory=dict)


class BrandUpdate(BaseModel):
    description: str | None = None
    default_language: str | None = None
    tone_name: str | None = None
    tone_instructions: str | None = None
    fallback_handoff_message: str | None = None
    public_reply_guidelines: str | None = None
    active: bool | None = None
    settings: dict[str, Any] | None = None


class BrandRuleCreate(BaseModel):
    category: str = "general"
    title: str
    content: str
    handoff_on_match: bool = False
    priority: int = 100


class StyleExampleCreate(BaseModel):
    title: str
    trigger_text: str
    ideal_reply: str
    notes: str | None = None
    priority: int = 100


class BrandRuleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    category: str
    title: str
    content: str
    handoff_on_match: bool
    priority: int
    created_at: datetime


class StyleExampleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    trigger_text: str
    ideal_reply: str
    notes: str | None
    priority: int
    created_at: datetime


class BrandOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    slug: str
    description: str | None
    default_language: str
    tone_name: str
    tone_instructions: str
    fallback_handoff_message: str
    public_reply_guidelines: str | None
    active: bool
    settings_json: dict[str, Any] | None
    created_at: datetime
    updated_at: datetime


class BrandWithSecretOut(BrandOut):
    api_key: str
