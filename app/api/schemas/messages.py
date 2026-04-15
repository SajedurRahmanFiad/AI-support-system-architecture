from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from app.api.schemas.conversations import AttachmentOut, MessageOut


class IncomingAttachmentRef(BaseModel):
    attachment_id: int


class MessageProcessRequest(BaseModel):
    brand_id: int
    channel: str = "api"
    customer_external_id: str
    customer_name: str | None = None
    customer_language: str | None = None
    conversation_external_id: str
    external_message_id: str | None = None
    text: str = ""
    attachment_ids: list[int] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    process_async: bool = False


class MessageProcessResponse(BaseModel):
    status: str
    conversation_id: int | None = None
    customer_id: int | None = None
    inbound_message_id: int | None = None
    outbound_message_id: int | None = None
    reply_text: str | None = None
    confidence: float | None = None
    handoff_reason: str | None = None
    flags: list[str] = Field(default_factory=list)
    used_sources: list[dict[str, Any]] = Field(default_factory=list)
    customer_updates: dict[str, Any] = Field(default_factory=dict)
    job_id: int | None = None


class FeedbackCreate(BaseModel):
    corrected_reply: str | None = None
    notes: str | None = None
    feedback_type: str = "correction"
    metadata: dict[str, Any] = Field(default_factory=dict)


class UploadResponse(BaseModel):
    attachment: AttachmentOut


class ReplyPreviewResponse(BaseModel):
    generated_at: datetime
    reply: MessageOut
