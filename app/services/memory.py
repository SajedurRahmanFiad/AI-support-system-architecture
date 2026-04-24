from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import models
from app.config import get_settings
from app.services.llm.base import BrandContext, ConversationTurn, CustomerSnapshot, LLMProvider


def build_brand_context(brand: models.Brand, *, system_prompt: str | None = None) -> BrandContext:
    rules = [
        {
            "category": item.category,
            "title": item.title,
            "content": item.content,
            "handoff_on_match": item.handoff_on_match,
            "priority": item.priority,
        }
        for item in sorted(brand.rules, key=lambda row: row.priority)
    ]
    style_examples = [
        {
            "title": item.title,
            "trigger_text": item.trigger_text,
            "ideal_reply": item.ideal_reply,
            "notes": item.notes,
            "priority": item.priority,
        }
        for item in sorted(brand.style_examples, key=lambda row: row.priority)
    ]
    return BrandContext(
        brand_id=brand.id,
        name=brand.name,
        default_language=brand.default_language,
        tone_name=brand.tone_name,
        tone_instructions=brand.tone_instructions,
        fallback_handoff_message=brand.fallback_handoff_message,
        public_reply_guidelines=brand.public_reply_guidelines,
        system_prompt=system_prompt,
        rules=rules,
        style_examples=style_examples,
    )


def build_customer_snapshot(customer: models.Customer) -> CustomerSnapshot:
    return CustomerSnapshot(
        display_name=customer.display_name,
        language=customer.language,
        city=customer.city,
        short_summary=customer.short_summary,
        profile=customer.profile_json or {},
        facts=[
            {
                "key": fact.fact_key,
                "value": fact.fact_value,
                "confidence": fact.confidence,
                "source": fact.source,
            }
            for fact in customer.facts
        ],
    )


def fetch_recent_history(db: Session, conversation_id: int) -> list[ConversationTurn]:
    settings = get_settings()
    statement = (
        select(models.Message)
        .where(models.Message.conversation_id == conversation_id)
        .order_by(models.Message.created_at.asc())
    )
    rows = list(db.scalars(statement))
    if len(rows) > settings.prompt_recent_message_limit:
        rows = rows[-settings.prompt_recent_message_limit :]
    return [ConversationTurn(role=row.role, text=row.text, created_at=row.created_at) for row in rows]


def apply_customer_updates(db: Session, customer: models.Customer, updates: dict) -> None:
    if not updates:
        return
    if updates.get("display_name"):
        customer.display_name = updates["display_name"]
    if updates.get("language"):
        customer.language = updates["language"]
    if updates.get("city"):
        customer.city = updates["city"]

    for item in updates.get("facts") or []:
        key = str(item.get("key", "")).strip()
        value = str(item.get("value", "")).strip()
        if not key or not value:
            continue
        existing = db.scalar(
            select(models.CustomerFact).where(
                models.CustomerFact.customer_id == customer.id,
                models.CustomerFact.fact_key == key,
            )
        )
        if existing:
            existing.fact_value = value
            existing.confidence = float(item.get("confidence", existing.confidence))
            existing.source = item.get("source", existing.source)
            db.add(existing)
        else:
            db.add(
                models.CustomerFact(
                    brand_id=customer.brand_id,
                    customer_id=customer.id,
                    fact_key=key,
                    fact_value=value,
                    confidence=float(item.get("confidence", 0.6)),
                    source=item.get("source", "llm"),
                )
            )
    db.add(customer)


def maybe_refresh_summary(
    db: Session,
    provider: LLMProvider,
    brand_context: BrandContext,
    customer: models.Customer,
    conversation: models.Conversation,
) -> None:
    settings = get_settings()
    message_count = db.scalar(
        select(func.count(models.Message.id)).where(models.Message.conversation_id == conversation.id)
    ) or 0
    if message_count < 3:
        return
    if conversation.short_summary and message_count % settings.summary_trigger_message_count != 0:
        return

    history = fetch_recent_history(db, conversation.id)
    try:
        summary = provider.summarize_conversation(brand_context, history)
    except Exception:
        # Skip summary refresh if LLM fails
        return
    if summary.summary:
        conversation.short_summary = summary.summary
        customer.short_summary = summary.summary
    for fact in summary.facts:
        apply_customer_updates(db, customer, {"facts": [fact]})
    db.add(conversation)
    db.add(customer)
