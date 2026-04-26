from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import TypeDecorator

from app.database import Base
from app.json_utils import to_json_compatible


class JSONText(TypeDecorator):
    impl = Text
    cache_ok = True

    def process_bind_param(self, value: Any, dialect: Any) -> str | None:
        if value is None:
            return None
        return json.dumps(to_json_compatible(value))

    def process_result_value(self, value: str | None, dialect: Any) -> Any:
        if value is None:
            return None
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return None


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class Brand(Base, TimestampMixin):
    __tablename__ = "brands"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    slug: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(255), unique=True)
    description: Mapped[str | None] = mapped_column(Text, default=None)
    default_language: Mapped[str] = mapped_column(String(20), default="bn-BD")
    tone_name: Mapped[str] = mapped_column(String(120), default="Helpful sales assistant")
    tone_instructions: Mapped[str] = mapped_column(Text, default="")
    fallback_handoff_message: Mapped[str] = mapped_column(
        Text,
        default="A human teammate will continue this conversation shortly.",
    )
    public_reply_guidelines: Mapped[str | None] = mapped_column(Text, default=None)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    api_key_hash: Mapped[str] = mapped_column(String(128), index=True)
    settings_json: Mapped[dict[str, Any] | None] = mapped_column(JSONText, default=dict)

    rules: Mapped[list[BrandRule]] = relationship(back_populates="brand", cascade="all, delete-orphan")
    style_examples: Mapped[list[StyleExample]] = relationship(back_populates="brand", cascade="all, delete-orphan")
    documents: Mapped[list[KnowledgeDocument]] = relationship(back_populates="brand", cascade="all, delete-orphan")
    customers: Mapped[list[Customer]] = relationship(back_populates="brand", cascade="all, delete-orphan")
    conversations: Mapped[list[Conversation]] = relationship(back_populates="brand", cascade="all, delete-orphan")
    product_images: Mapped[list[ProductImage]] = relationship(back_populates="brand", cascade="all, delete-orphan")
    facebook_pages: Mapped[list[FacebookPageAutomation]] = relationship(back_populates="brand", cascade="all, delete-orphan")
    payments: Mapped[list[BrandPayment]] = relationship(back_populates="brand", cascade="all, delete-orphan")
    usage_records: Mapped[list[UsageRecord]] = relationship(back_populates="brand", cascade="all, delete-orphan")


class BrandRule(Base, TimestampMixin):
    __tablename__ = "brand_rules"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    brand_id: Mapped[int] = mapped_column(ForeignKey("brands.id", ondelete="CASCADE"), index=True)
    category: Mapped[str] = mapped_column(String(64), default="general")
    title: Mapped[str] = mapped_column(String(255))
    content: Mapped[str] = mapped_column(Text)
    handoff_on_match: Mapped[bool] = mapped_column(Boolean, default=False)
    priority: Mapped[int] = mapped_column(Integer, default=100)

    brand: Mapped[Brand] = relationship(back_populates="rules")


class StyleExample(Base, TimestampMixin):
    __tablename__ = "style_examples"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    brand_id: Mapped[int] = mapped_column(ForeignKey("brands.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(255))
    trigger_text: Mapped[str] = mapped_column(Text)
    ideal_reply: Mapped[str] = mapped_column(Text)
    notes: Mapped[str | None] = mapped_column(Text, default=None)
    priority: Mapped[int] = mapped_column(Integer, default=100)

    brand: Mapped[Brand] = relationship(back_populates="style_examples")


class KnowledgeDocument(Base, TimestampMixin):
    __tablename__ = "knowledge_documents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    brand_id: Mapped[int] = mapped_column(ForeignKey("brands.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(255))
    source_type: Mapped[str] = mapped_column(String(64), default="faq")
    source_reference: Mapped[str | None] = mapped_column(String(500), default=None)
    raw_text: Mapped[str] = mapped_column(Text)
    metadata_json: Mapped[dict[str, Any] | None] = mapped_column(JSONText, default=dict)
    status: Mapped[str] = mapped_column(String(40), default="ready")

    brand: Mapped[Brand] = relationship(back_populates="documents")
    chunks: Mapped[list[KnowledgeChunk]] = relationship(back_populates="document", cascade="all, delete-orphan")


class KnowledgeChunk(Base, TimestampMixin):
    __tablename__ = "knowledge_chunks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    brand_id: Mapped[int] = mapped_column(ForeignKey("brands.id", ondelete="CASCADE"), index=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("knowledge_documents.id", ondelete="CASCADE"), index=True)
    chunk_index: Mapped[int] = mapped_column(Integer)
    content: Mapped[str] = mapped_column(Text)
    token_estimate: Mapped[int] = mapped_column(Integer, default=0)
    embedding_json: Mapped[list[float] | None] = mapped_column(JSONText, default=None)
    metadata_json: Mapped[dict[str, Any] | None] = mapped_column(JSONText, default=dict)

    document: Mapped[KnowledgeDocument] = relationship(back_populates="chunks")

    __table_args__ = (UniqueConstraint("document_id", "chunk_index", name="uq_document_chunk_index"),)


class Customer(Base, TimestampMixin):
    __tablename__ = "customers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    brand_id: Mapped[int] = mapped_column(ForeignKey("brands.id", ondelete="CASCADE"), index=True)
    external_id: Mapped[str] = mapped_column(String(255))
    display_name: Mapped[str | None] = mapped_column(String(255), default=None)
    language: Mapped[str | None] = mapped_column(String(20), default=None)
    city: Mapped[str | None] = mapped_column(String(120), default=None)
    profile_json: Mapped[dict[str, Any] | None] = mapped_column(JSONText, default=dict)
    short_summary: Mapped[str | None] = mapped_column(Text, default=None)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)

    brand: Mapped[Brand] = relationship(back_populates="customers")
    facts: Mapped[list[CustomerFact]] = relationship(back_populates="customer", cascade="all, delete-orphan")
    conversations: Mapped[list[Conversation]] = relationship(back_populates="customer")

    __table_args__ = (UniqueConstraint("brand_id", "external_id", name="uq_customer_brand_external"),)


class CustomerFact(Base, TimestampMixin):
    __tablename__ = "customer_facts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    brand_id: Mapped[int] = mapped_column(ForeignKey("brands.id", ondelete="CASCADE"), index=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id", ondelete="CASCADE"), index=True)
    fact_key: Mapped[str] = mapped_column(String(120))
    fact_value: Mapped[str] = mapped_column(Text)
    confidence: Mapped[float] = mapped_column(Float, default=0.5)
    source: Mapped[str] = mapped_column(String(120), default="system")

    customer: Mapped[Customer] = relationship(back_populates="facts")


class Conversation(Base, TimestampMixin):
    __tablename__ = "conversations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    brand_id: Mapped[int] = mapped_column(ForeignKey("brands.id", ondelete="CASCADE"), index=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id", ondelete="CASCADE"), index=True)
    channel: Mapped[str] = mapped_column(String(64), default="api")
    external_conversation_id: Mapped[str] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(40), default="open")
    owner_type: Mapped[str] = mapped_column(String(40), default="ai")
    owner_name: Mapped[str | None] = mapped_column(String(120), default=None)
    short_summary: Mapped[str | None] = mapped_column(Text, default=None)
    metadata_json: Mapped[dict[str, Any] | None] = mapped_column(JSONText, default=dict)
    last_message_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)

    brand: Mapped[Brand] = relationship(back_populates="conversations")
    customer: Mapped[Customer] = relationship(back_populates="conversations")
    messages: Mapped[list[Message]] = relationship(back_populates="conversation", cascade="all, delete-orphan")

    __table_args__ = (
        UniqueConstraint("brand_id", "external_conversation_id", name="uq_conversation_brand_external"),
        Index("ix_conversations_brand_updated_at", "brand_id", "updated_at"),
        Index("ix_conversations_brand_last_message_at", "brand_id", "last_message_at"),
    )


class Message(Base, TimestampMixin):
    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    brand_id: Mapped[int] = mapped_column(ForeignKey("brands.id", ondelete="CASCADE"), index=True)
    conversation_id: Mapped[int] = mapped_column(ForeignKey("conversations.id", ondelete="CASCADE"), index=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id", ondelete="CASCADE"), index=True)
    external_message_id: Mapped[str | None] = mapped_column(String(255), default=None, index=True)
    role: Mapped[str] = mapped_column(String(40))
    source: Mapped[str] = mapped_column(String(64), default="api")
    text: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(40), default="received")
    confidence: Mapped[float | None] = mapped_column(Float, default=None)
    handoff_reason: Mapped[str | None] = mapped_column(Text, default=None)
    used_sources_json: Mapped[list[dict[str, Any]] | None] = mapped_column(JSONText, default=list)
    flags_json: Mapped[list[str] | None] = mapped_column(JSONText, default=list)
    token_usage_json: Mapped[dict[str, Any] | None] = mapped_column(JSONText, default=dict)

    conversation: Mapped[Conversation] = relationship(back_populates="messages")
    attachments: Mapped[list[Attachment]] = relationship(back_populates="message", cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_messages_conversation_created_at", "conversation_id", "created_at"),
        Index("ix_messages_brand_created_at", "brand_id", "created_at"),
    )


class Attachment(Base, TimestampMixin):
    __tablename__ = "attachments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    brand_id: Mapped[int] = mapped_column(ForeignKey("brands.id", ondelete="CASCADE"), index=True)
    conversation_id: Mapped[int | None] = mapped_column(ForeignKey("conversations.id", ondelete="SET NULL"), index=True)
    customer_id: Mapped[int | None] = mapped_column(ForeignKey("customers.id", ondelete="SET NULL"), index=True)
    message_id: Mapped[int | None] = mapped_column(ForeignKey("messages.id", ondelete="SET NULL"), index=True)
    attachment_type: Mapped[str] = mapped_column(String(40))
    mime_type: Mapped[str] = mapped_column(String(120))
    original_filename: Mapped[str | None] = mapped_column(String(255), default=None)
    storage_path: Mapped[str] = mapped_column(String(500))
    transcript: Mapped[str | None] = mapped_column(Text, default=None)
    translated_text: Mapped[str | None] = mapped_column(Text, default=None)
    extracted_text: Mapped[str | None] = mapped_column(Text, default=None)
    detected_language: Mapped[str | None] = mapped_column(String(20), default=None)
    analysis_confidence: Mapped[float | None] = mapped_column(Float, default=None)
    metadata_json: Mapped[dict[str, Any] | None] = mapped_column(JSONText, default=dict)

    message: Mapped[Message | None] = relationship(back_populates="attachments")


class FeedbackEvent(Base, TimestampMixin):
    __tablename__ = "feedback_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    brand_id: Mapped[int] = mapped_column(ForeignKey("brands.id", ondelete="CASCADE"), index=True)
    conversation_id: Mapped[int | None] = mapped_column(ForeignKey("conversations.id", ondelete="SET NULL"), index=True)
    message_id: Mapped[int | None] = mapped_column(ForeignKey("messages.id", ondelete="SET NULL"), index=True)
    feedback_type: Mapped[str] = mapped_column(String(40), default="correction")
    corrected_reply: Mapped[str | None] = mapped_column(Text, default=None)
    notes: Mapped[str | None] = mapped_column(Text, default=None)
    metadata_json: Mapped[dict[str, Any] | None] = mapped_column(JSONText, default=dict)


class Job(Base, TimestampMixin):
    __tablename__ = "jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    brand_id: Mapped[int | None] = mapped_column(ForeignKey("brands.id", ondelete="SET NULL"), index=True)
    kind: Mapped[str] = mapped_column(String(120), index=True)
    status: Mapped[str] = mapped_column(String(40), default="pending", index=True)
    payload_json: Mapped[dict[str, Any] | None] = mapped_column(JSONText, default=dict)
    result_json: Mapped[dict[str, Any] | None] = mapped_column(JSONText, default=dict)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    available_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    locked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    last_error: Mapped[str | None] = mapped_column(Text, default=None)

    __table_args__ = (
        Index("ix_jobs_status_available_created", "status", "available_at", "created_at"),
    )


class AuditLog(Base, TimestampMixin):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    brand_id: Mapped[int | None] = mapped_column(ForeignKey("brands.id", ondelete="SET NULL"), index=True)
    conversation_id: Mapped[int | None] = mapped_column(ForeignKey("conversations.id", ondelete="SET NULL"), index=True)
    message_id: Mapped[int | None] = mapped_column(ForeignKey("messages.id", ondelete="SET NULL"), index=True)
    event_type: Mapped[str] = mapped_column(String(80), index=True)
    request_json: Mapped[dict[str, Any] | None] = mapped_column(JSONText, default=dict)
    response_json: Mapped[dict[str, Any] | None] = mapped_column(JSONText, default=dict)


class ProductImage(Base, TimestampMixin):
    __tablename__ = "product_images"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    brand_id: Mapped[int] = mapped_column(ForeignKey("brands.id", ondelete="CASCADE"), index=True)
    product_name: Mapped[str] = mapped_column(String(255))
    product_category: Mapped[str] = mapped_column(String(120))
    storage_path: Mapped[str] = mapped_column(String(500))
    image_embedding: Mapped[list[float] | None] = mapped_column(JSONText, default=None)
    product_metadata: Mapped[dict[str, Any] | None] = mapped_column(JSONText, default=dict)

    brand: Mapped[Brand] = relationship(back_populates="product_images")


class FacebookPageAutomation(Base, TimestampMixin):
    __tablename__ = "facebook_page_automations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    brand_id: Mapped[int] = mapped_column(ForeignKey("brands.id", ondelete="CASCADE"), index=True)
    page_name: Mapped[str] = mapped_column(String(255))
    page_id: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    page_username: Mapped[str | None] = mapped_column(String(255), default=None)
    app_id: Mapped[str] = mapped_column(String(255))
    app_secret: Mapped[str] = mapped_column(Text)
    page_access_token: Mapped[str] = mapped_column(Text)
    verify_token: Mapped[str] = mapped_column(Text)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    automation_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    reply_to_messages: Mapped[bool] = mapped_column(Boolean, default=True)
    reply_to_comments: Mapped[bool] = mapped_column(Boolean, default=False)
    private_reply_to_comments: Mapped[bool] = mapped_column(Boolean, default=False)
    auto_hide_spam_comments: Mapped[bool] = mapped_column(Boolean, default=False)
    handoff_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    business_hours_only: Mapped[bool] = mapped_column(Boolean, default=False)
    reply_delay_seconds: Mapped[int] = mapped_column(Integer, default=15)
    allowed_reply_window_hours: Mapped[int] = mapped_column(Integer, default=24)
    default_language: Mapped[str] = mapped_column(String(20), default="bn-BD")
    timezone: Mapped[str] = mapped_column(String(64), default="Asia/Dhaka")
    live_server_label: Mapped[str | None] = mapped_column(String(255), default=None)
    notes: Mapped[str | None] = mapped_column(Text, default=None)

    brand: Mapped[Brand] = relationship(back_populates="facebook_pages")


class AppSetting(Base, TimestampMixin):
    __tablename__ = "app_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    setting_key: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    value_json: Mapped[dict[str, Any] | None] = mapped_column(JSONText, default=dict)


class UsageRecord(Base, TimestampMixin):
    __tablename__ = "usage_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    brand_id: Mapped[int] = mapped_column(ForeignKey("brands.id", ondelete="CASCADE"), index=True)
    conversation_id: Mapped[int | None] = mapped_column(ForeignKey("conversations.id", ondelete="SET NULL"), index=True)
    message_id: Mapped[int | None] = mapped_column(ForeignKey("messages.id", ondelete="SET NULL"), index=True)
    channel: Mapped[str] = mapped_column(String(64), default="api", index=True)
    usage_type: Mapped[str] = mapped_column(String(40), default="text", index=True)
    provider: Mapped[str | None] = mapped_column(String(64), default=None)
    model: Mapped[str | None] = mapped_column(String(255), default=None)
    message_units: Mapped[int] = mapped_column(Integer, default=0)
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    billed_amount_bdt: Mapped[float] = mapped_column(Float, default=0.0)
    actual_cost_bdt: Mapped[float] = mapped_column(Float, default=0.0)
    metadata_json: Mapped[dict[str, Any] | None] = mapped_column(JSONText, default=dict)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)

    brand: Mapped[Brand] = relationship(back_populates="usage_records")

    __table_args__ = (
        Index("ix_usage_records_brand_occurred_at", "brand_id", "occurred_at"),
        Index("ix_usage_records_brand_usage_type_occurred_at", "brand_id", "usage_type", "occurred_at"),
    )


class BrandPayment(Base, TimestampMixin):
    __tablename__ = "brand_payments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    brand_id: Mapped[int] = mapped_column(ForeignKey("brands.id", ondelete="CASCADE"), index=True)
    amount_bdt: Mapped[float] = mapped_column(Float, default=0.0)
    paid_on: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)
    notes: Mapped[str | None] = mapped_column(Text, default=None)
    metadata_json: Mapped[dict[str, Any] | None] = mapped_column(JSONText, default=dict)

    brand: Mapped[Brand] = relationship(back_populates="payments")

    __table_args__ = (
        Index("ix_brand_payments_brand_paid_on", "brand_id", "paid_on"),
    )
