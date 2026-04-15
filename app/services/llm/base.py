from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class KnowledgeSnippet:
    chunk_id: int
    document_id: int
    title: str
    content: str
    score: float


@dataclass
class AttachmentInsight:
    attachment_id: int
    attachment_type: str
    summary: str
    transcript: str | None = None
    extracted_text: str | None = None


@dataclass
class ConversationTurn:
    role: str
    text: str
    created_at: datetime | None = None


@dataclass
class CustomerSnapshot:
    display_name: str | None
    language: str | None
    city: str | None
    short_summary: str | None
    profile: dict[str, Any] = field(default_factory=dict)
    facts: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class BrandContext:
    brand_id: int
    name: str
    default_language: str
    tone_name: str
    tone_instructions: str
    fallback_handoff_message: str
    public_reply_guidelines: str | None
    rules: list[dict[str, Any]] = field(default_factory=list)
    style_examples: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class ReplyDecision:
    status: str
    reply_text: str
    confidence: float
    handoff_reason: str | None = None
    customer_updates: dict[str, Any] = field(default_factory=dict)
    flags: list[str] = field(default_factory=list)
    used_knowledge_ids: list[int] = field(default_factory=list)
    internal_notes: str | None = None
    token_usage: dict[str, Any] = field(default_factory=dict)


@dataclass
class SummaryResult:
    summary: str
    facts: list[dict[str, Any]] = field(default_factory=list)


class LLMProvider(ABC):
    provider_name: str = "base"

    @abstractmethod
    def generate_reply(
        self,
        brand: BrandContext,
        customer: CustomerSnapshot,
        history: list[ConversationTurn],
        incoming_text: str,
        knowledge: list[KnowledgeSnippet],
        attachment_insights: list[AttachmentInsight],
    ) -> ReplyDecision:
        raise NotImplementedError

    @abstractmethod
    def summarize_conversation(
        self,
        brand: BrandContext,
        history: list[ConversationTurn],
    ) -> SummaryResult:
        raise NotImplementedError

    @abstractmethod
    def analyze_attachment(self, attachment_type: str, mime_type: str, data: bytes) -> AttachmentInsight:
        raise NotImplementedError

    @abstractmethod
    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        raise NotImplementedError
