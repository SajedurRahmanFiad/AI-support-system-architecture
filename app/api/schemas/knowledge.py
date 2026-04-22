from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


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


class KnowledgeConversationTranscriptMessage(BaseModel):
    role: Literal["customer", "assistant"]
    text: str

    @field_validator("text")
    @classmethod
    def validate_text(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Message text is required.")
        return cleaned


class KnowledgeManualConversationExampleCreate(BaseModel):
    brand_id: int | None = None
    global_example: bool = False
    customer_text: str | None = None
    approved_reply: str | None = None
    original_reply: str | None = None
    title: str | None = None
    source_reference: str | None = None
    notes: str | None = None
    messages: list[KnowledgeConversationTranscriptMessage] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_entry_shape(self) -> "KnowledgeManualConversationExampleCreate":
        if not self.global_example and not self.brand_id:
            raise ValueError("brand_id is required unless global_example is true.")

        has_transcript = len(self.messages) > 0
        has_customer_text = bool(self.customer_text and self.customer_text.strip())
        has_approved_reply = bool(self.approved_reply and self.approved_reply.strip())

        if not has_transcript and not (has_customer_text and has_approved_reply):
            raise ValueError("Provide either a transcript in messages or both customer_text and approved_reply.")

        if has_transcript:
            roles = {message.role for message in self.messages}
            if "customer" not in roles:
                raise ValueError("Transcript examples must include at least one customer message.")
            if "assistant" not in roles:
                raise ValueError("Transcript examples must include at least one assistant message.")

        return self


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
