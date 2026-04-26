from __future__ import annotations

from fastapi import HTTPException, status
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app import models
from app.api.schemas.messages import MessageProcessRequest, MessageProcessResponse


def deliver_external_reply_if_needed(
    db: Session,
    payload: MessageProcessRequest,
    result: MessageProcessResponse,
) -> dict[str, str | None]:
    if payload.channel != "facebook_messenger":
        return {"status": "skipped", "provider_message_id": None, "pending_review_label": None}

    metadata = payload.metadata or {}
    page_id = str(metadata.get("page_id") or "").strip()
    recipient_id = str(metadata.get("sender_id") or payload.customer_external_id or "").strip()
    if not page_id or not recipient_id:
        label_state = _sync_pending_review_label_for_result(db, result)
        return {"status": "skipped", "provider_message_id": None, "pending_review_label": label_state}

    from app.services.facebook_webhooks import FacebookMessengerClient, FacebookMessengerDeliveryError

    page = db.scalar(select(models.FacebookPageAutomation).where(models.FacebookPageAutomation.page_id == page_id))
    if page is None or not page.page_access_token:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Facebook page {page_id} is not configured for outbound delivery.",
        )

    outbound_message_id = result.outbound_message_id
    if not outbound_message_id:
        label_state = _sync_pending_review_label_for_result(db, result)
        return {"status": "no_reply", "provider_message_id": None, "pending_review_label": label_state}

    outbound_row = db.execute(
        select(
            models.Message.id,
            models.Message.external_message_id,
            models.Message.text,
        ).where(models.Message.id == outbound_message_id)
    ).one_or_none()
    if outbound_row is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Generated reply {outbound_message_id} could not be loaded for Facebook delivery.",
        )

    existing_delivery_id = str(outbound_row.external_message_id or "").strip()
    if existing_delivery_id:
        label_state = _sync_pending_review_label_for_result(db, result)
        return {"status": "already_sent", "provider_message_id": existing_delivery_id, "pending_review_label": label_state}

    reply_text = (result.reply_text or outbound_row.text or "").strip()
    if not reply_text:
        label_state = _sync_pending_review_label_for_result(db, result)
        return {"status": "no_reply", "provider_message_id": None, "pending_review_label": label_state}

    try:
        delivery = FacebookMessengerClient(page.page_access_token).send_text_message(
            recipient_id=recipient_id,
            text=reply_text,
        )
    except FacebookMessengerDeliveryError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc

    sent_message_id = str(delivery.get("message_id") or "").strip() or f"facebook-sent:{outbound_message_id}"
    update_result = db.execute(
        update(models.Message)
        .where(models.Message.id == outbound_message_id)
        .values(external_message_id=sent_message_id)
        .execution_options(synchronize_session=False)
    )
    if update_result.rowcount == 0:
        persisted_delivery_id = db.scalar(select(models.Message.external_message_id).where(models.Message.id == outbound_message_id))
        if str(persisted_delivery_id or "").strip():
            db.rollback()
            return {"status": "already_sent", "provider_message_id": str(persisted_delivery_id)}
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Generated reply {outbound_message_id} could not be marked as delivered.",
        )

    db.commit()
    label_state = _sync_pending_review_label_for_result(db, result)
    return {"status": "sent", "provider_message_id": sent_message_id, "pending_review_label": label_state}


def _sync_pending_review_label_for_result(db: Session, result: MessageProcessResponse) -> str | None:
    if not result.conversation_id:
        return None

    conversation = db.get(models.Conversation, result.conversation_id)
    if conversation is None:
        return None

    from app.services.facebook_webhooks import sync_pending_review_label

    enabled = result.status == "handoff"
    changed = sync_pending_review_label(db, conversation, enabled)
    if changed:
        return "applied" if enabled else "removed"
    return "unchanged"
