from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import joinedload

from app import models
from app.api.deps import DbSession, require_platform_access
from app.api.schemas.conversations import ConversationOut, ConversationSummaryOut, HandoffRequest
from app.services.facebook_webhooks import sync_pending_review_label

router = APIRouter(prefix="/v1/conversations", dependencies=[Depends(require_platform_access)])


def _serialize_conversation(conversation: models.Conversation) -> ConversationOut:
    payload = ConversationOut.model_validate(conversation).model_dump()
    payload["customer_display_name"] = conversation.customer.display_name if getattr(conversation, "customer", None) else None
    return ConversationOut(**payload)


@router.get("/summary", response_model=list[ConversationSummaryOut])
def list_conversation_summaries(brand_id: int, db: DbSession) -> list[ConversationSummaryOut]:
    last_message_text = (
        select(models.Message.text)
        .where(models.Message.conversation_id == models.Conversation.id)
        .order_by(models.Message.created_at.desc())
        .limit(1)
        .scalar_subquery()
    )
    statement = (
        select(models.Conversation, models.Customer.display_name, last_message_text.label("last_message_text"))
        .join(models.Customer, models.Customer.id == models.Conversation.customer_id)
        .where(models.Conversation.brand_id == brand_id)
        .order_by(models.Conversation.updated_at.desc())
    )
    rows = db.execute(statement).all()
    summaries: list[ConversationSummaryOut] = []
    for conversation, customer_display_name, preview_text in rows:
        payload = ConversationSummaryOut.model_validate(conversation).model_dump()
        payload["last_message_text"] = preview_text
        payload["customer_display_name"] = customer_display_name
        summaries.append(ConversationSummaryOut(**payload))
    return summaries


@router.get("", response_model=list[ConversationOut])
def list_conversations(brand_id: int, db: DbSession) -> list[models.Conversation]:
    statement = (
        select(models.Conversation)
        .options(
            joinedload(models.Conversation.customer),
            joinedload(models.Conversation.messages).joinedload(models.Message.attachments),
        )
        .where(models.Conversation.brand_id == brand_id)
        .order_by(models.Conversation.updated_at.desc())
    )
    return [_serialize_conversation(item) for item in db.execute(statement).unique().scalars().all()]


@router.get("/{conversation_id}", response_model=ConversationOut)
def get_conversation(conversation_id: int, db: DbSession) -> models.Conversation:
    statement = (
        select(models.Conversation)
        .options(
            joinedload(models.Conversation.customer),
            joinedload(models.Conversation.messages).joinedload(models.Message.attachments),
        )
        .where(models.Conversation.id == conversation_id)
    )
    row = db.execute(statement).unique().scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found.")
    return _serialize_conversation(row)


@router.post("/{conversation_id}/handoff", response_model=ConversationOut)
def handoff_conversation(conversation_id: int, payload: HandoffRequest, db: DbSession) -> models.Conversation:
    conversation = db.get(models.Conversation, conversation_id)
    if not conversation:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found.")
    conversation.status = "handoff"
    conversation.owner_type = "human"
    conversation.owner_name = payload.owner_name
    conversation.updated_at = datetime.now(timezone.utc)
    db.add(conversation)
    db.commit()
    db.refresh(conversation)
    sync_pending_review_label(db, conversation, True)
    db.refresh(conversation)
    return _serialize_conversation(db.get(models.Conversation, conversation.id))


@router.post("/{conversation_id}/release", response_model=ConversationOut)
def release_conversation(conversation_id: int, db: DbSession) -> models.Conversation:
    conversation = db.get(models.Conversation, conversation_id)
    if not conversation:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found.")
    conversation.status = "open"
    conversation.owner_type = "ai"
    conversation.owner_name = None
    conversation.updated_at = datetime.now(timezone.utc)
    db.add(conversation)
    db.commit()
    db.refresh(conversation)
    sync_pending_review_label(db, conversation, False)
    db.refresh(conversation)
    reloaded = db.execute(
        select(models.Conversation)
        .options(
            joinedload(models.Conversation.customer),
            joinedload(models.Conversation.messages).joinedload(models.Message.attachments),
        )
        .where(models.Conversation.id == conversation.id)
    ).unique().scalar_one()
    return _serialize_conversation(reloaded)
