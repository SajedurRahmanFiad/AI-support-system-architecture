from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import joinedload

from app import models
from app.api.deps import DbSession, require_platform_access
from app.api.schemas.feedback import FeedbackEventOut, FeedbackEventUpdate

router = APIRouter(prefix="/v1/feedback", dependencies=[Depends(require_platform_access)])


def _serialize_feedback_event(row: models.FeedbackEvent, db: DbSession) -> FeedbackEventOut:
    message = db.get(models.Message, row.message_id) if row.message_id else None
    previous_customer_text = None
    if message and row.conversation_id:
        previous_customer = db.scalar(
            select(models.Message)
            .where(
                models.Message.conversation_id == row.conversation_id,
                models.Message.role == "customer",
                models.Message.created_at <= message.created_at,
            )
            .order_by(models.Message.created_at.desc())
        )
        if previous_customer:
            previous_customer_text = previous_customer.text
    return FeedbackEventOut(
        id=row.id,
        brand_id=row.brand_id,
        conversation_id=row.conversation_id,
        message_id=row.message_id,
        feedback_type=row.feedback_type,
        corrected_reply=row.corrected_reply,
        notes=row.notes,
        metadata_json=row.metadata_json,
        created_at=row.created_at,
        updated_at=row.updated_at,
        message_text=message.text if message else None,
        message_status=message.status if message else None,
        previous_customer_text=previous_customer_text,
    )


@router.get("", response_model=list[FeedbackEventOut])
def list_feedback(
    db: DbSession,
    brand_id: int | None = None,
    limit: int = 100,
) -> list[FeedbackEventOut]:
    statement = select(models.FeedbackEvent).order_by(models.FeedbackEvent.created_at.desc()).limit(max(1, min(limit, 500)))
    if brand_id is not None:
        statement = statement.where(models.FeedbackEvent.brand_id == brand_id)
    rows = list(db.scalars(statement))
    return [_serialize_feedback_event(row, db) for row in rows]


@router.patch("/{feedback_id}", response_model=FeedbackEventOut)
def update_feedback(feedback_id: int, payload: FeedbackEventUpdate, db: DbSession) -> FeedbackEventOut:
    row = db.get(models.FeedbackEvent, feedback_id)
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Feedback event not found.")
    for field, value in payload.model_dump(exclude_unset=True).items():
        if field == "metadata":
            row.metadata_json = value
        else:
            setattr(row, field, value)
    db.add(row)
    db.commit()
    db.refresh(row)
    return _serialize_feedback_event(row, db)
