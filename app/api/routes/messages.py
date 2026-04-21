from fastapi import APIRouter, Depends, HTTPException, Security, status
from sqlalchemy.orm import Session

from app import models
from app.api.deps import brand_token_header, platform_token_header, require_platform_access
from app.api.schemas.messages import FeedbackCreate, MessageProcessRequest, MessageProcessResponse
from app.config import get_settings
from app.database import get_db
from app.services.brand_service import require_brand_access
from app.services.jobs import enqueue_job
from app.services.orchestrator import MessageProcessor

router = APIRouter(prefix="/messages")


@router.post("/process", response_model=MessageProcessResponse)
def process_message(
    payload: MessageProcessRequest,
    db: Session = Depends(get_db),
    brand_token: str | None = Security(brand_token_header),
    platform_token: str | None = Security(platform_token_header),
) -> MessageProcessResponse:
    require_brand_access(db, payload.brand_id, brand_token, platform_token, get_settings().platform_api_token)
    if payload.process_async:
        job = enqueue_job(db, "process_message", payload.model_dump(), payload.brand_id)
        return MessageProcessResponse(status="queued", job_id=job.id)
    return MessageProcessor(db).process(payload)


@router.post("/{message_id}/feedback")
def create_feedback(
    message_id: int,
    payload: FeedbackCreate,
    db: Session = Depends(get_db),
    _: None = Depends(require_platform_access),
) -> dict[str, str]:
    message = db.get(models.Message, message_id)
    if not message:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Message not found.")
    row = models.FeedbackEvent(
        brand_id=message.brand_id,
        conversation_id=message.conversation_id,
        message_id=message.id,
        feedback_type=payload.feedback_type,
        corrected_reply=payload.corrected_reply,
        notes=payload.notes,
        metadata_json=payload.metadata,
    )
    db.add(row)
    db.commit()
    return {"status": "saved"}
