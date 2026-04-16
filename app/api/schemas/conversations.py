from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class AttachmentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    brand_id: int
    conversation_id: int | None
    customer_id: int | None
    message_id: int | None
    attachment_type: str
    mime_type: str
    original_filename: str | None
    storage_path: str
    transcript: str | None
    translated_text: str | None
    extracted_text: str | None
    detected_language: str | None
    analysis_confidence: float | None
    metadata_json: dict[str, Any] | None
    created_at: datetime
    updated_at: datetime


class MessageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    external_message_id: str | None
    role: str
    source: str
    text: str
    status: str
    confidence: float | None
    handoff_reason: str | None
    used_sources_json: list[dict[str, Any]] | None
    flags_json: list[str] | None
    token_usage_json: dict[str, Any] | None
    created_at: datetime
    attachments: list[AttachmentOut] = Field(default_factory=list)


class ConversationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    brand_id: int
    customer_id: int
    channel: str
    external_conversation_id: str
    status: str
    owner_type: str
    owner_name: str | None
    short_summary: str | None
    metadata_json: dict[str, Any] | None
    last_message_at: datetime | None
    created_at: datetime
    updated_at: datetime
    messages: list[MessageOut] = Field(default_factory=list)


class HandoffRequest(BaseModel):
    owner_name: str | None = None
    notes: str | None = None
