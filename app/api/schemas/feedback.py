from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class FeedbackEventOut(BaseModel):
    id: int
    brand_id: int
    conversation_id: int | None
    message_id: int | None
    feedback_type: str
    corrected_reply: str | None
    notes: str | None
    metadata_json: dict[str, Any] | None
    created_at: datetime
    updated_at: datetime
    message_text: str | None = None
    message_status: str | None = None
    previous_customer_text: str | None = None


class FeedbackEventUpdate(BaseModel):
    corrected_reply: str | None = None
    notes: str | None = None
    feedback_type: str | None = None
    metadata: dict[str, Any] | None = Field(default=None)
