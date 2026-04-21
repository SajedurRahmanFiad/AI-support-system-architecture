from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import joinedload

from app import models
from app.api.deps import DbSession, require_platform_access
from app.api.schemas.conversations import ConversationOut, ConversationSummaryOut, HandoffRequest

router = APIRouter(prefix="/v1/conversations", dependencies=[Depends(require_platform_access)])


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
        select(models.Conversation, last_message_text.label("last_message_text"))
        .where(models.Conversation.brand_id == brand_id)
        .order_by(models.Conversation.updated_at.desc())
    )
    rows = db.execute(statement).all()
    summaries: list[ConversationSummaryOut] = []
    for conversation, preview_text in rows:
        payload = ConversationSummaryOut.model_validate(conversation).model_dump()
        payload["last_message_text"] = preview_text
        summaries.append(ConversationSummaryOut(**payload))
    return summaries


@router.get("", response_model=list[ConversationOut])
def list_conversations(brand_id: int, db: DbSession) -> list[models.Conversation]:
    statement = (
        select(models.Conversation)
        .options(joinedload(models.Conversation.messages).joinedload(models.Message.attachments))
        .where(models.Conversation.brand_id == brand_id)
        .order_by(models.Conversation.updated_at.desc())
    )
    return list(db.execute(statement).unique().scalars().all())


@router.get("/{conversation_id}", response_model=ConversationOut)
def get_conversation(conversation_id: int, db: DbSession) -> models.Conversation:
    statement = (
        select(models.Conversation)
        .options(joinedload(models.Conversation.messages).joinedload(models.Message.attachments))
        .where(models.Conversation.id == conversation_id)
    )
    row = db.execute(statement).unique().scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found.")
    return row


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
    return conversation


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
    return conversation
