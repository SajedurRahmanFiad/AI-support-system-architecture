from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel


class AuditLogOut(BaseModel):
    id: int
    brand_id: int | None
    conversation_id: int | None
    message_id: int | None
    event_type: str
    request_json: dict[str, Any] | None
    response_json: dict[str, Any] | None
    created_at: datetime
    updated_at: datetime
