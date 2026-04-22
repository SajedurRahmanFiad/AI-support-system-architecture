from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class KnowledgeDocumentCreate(BaseModel):
    brand_id: int
    title: str
    source_type: str = "faq"
    source_reference: str | None = None
    raw_text: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    process_async: bool = False


class KnowledgeDocumentUpdate(BaseModel):
    title: str | None = None
    source_type: str | None = None
    source_reference: str | None = None
    raw_text: str | None = None
    metadata: dict[str, Any] | None = None


class KnowledgeConversationExampleCreate(BaseModel):
    brand_id: int
    conversation_id: int
    customer_message_id: int
    assistant_message_id: int | None = None
    approved_reply: str
    title: str | None = None
    source_reference: str | None = None
    notes: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class KnowledgeReindexRequest(BaseModel):
    process_async: bool = False


class KnowledgeDocumentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    brand_id: int
    title: str
    source_type: str
    source_reference: str | None
    raw_text: str
    metadata_json: dict[str, Any] | None
    status: str
    created_at: datetime
    updated_at: datetime


class KnowledgeSearchRequest(BaseModel):
    brand_id: int
    query: str
    top_k: int = 5


class KnowledgeSearchHit(BaseModel):
    chunk_id: int
    document_id: int
    title: str
    content: str
    score: float


class KnowledgeSearchResponse(BaseModel):
    hits: list[KnowledgeSearchHit]
