from __future__ import annotations

import hashlib
import hmac
import json
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import models
from app.api.schemas.messages import MessageProcessRequest
from app.services.orchestrator import MessageProcessor


class FacebookWebhookService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def verify_subscription(self, mode: str, verify_token: str, challenge: str) -> str:
        normalized_mode = mode.strip().lower()
        normalized_token = verify_token.strip()
        if normalized_mode != "subscribe" or not normalized_token:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid Facebook webhook verification request.")

        page = self.db.scalar(
            select(models.FacebookPageAutomation).where(models.FacebookPageAutomation.verify_token == normalized_token)
        )
        if not page:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Facebook verify token did not match any saved page.")

        return challenge

    def handle_payload(self, raw_body: bytes, signature_header: str | None = None) -> dict[str, Any]:
        try:
            payload = json.loads(raw_body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid Facebook webhook JSON payload.") from exc

        if not isinstance(payload, dict):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Facebook webhook payload must be a JSON object.")

        if payload.get("object") != "page":
            return {
                "status": "ignored",
                "processed": 0,
                "ignored": 1,
                "errors": 0,
                "event_count": 0,
                "details": ["Unsupported Facebook webhook object."],
            }

        self._verify_signature_if_present(raw_body, signature_header, payload)

        processed = 0
        ignored = 0
        errors = 0
        details: list[str] = []

        for entry in payload.get("entry", []):
            entry_processed, entry_ignored, entry_errors, entry_details = self._handle_entry(entry)
            processed += entry_processed
            ignored += entry_ignored
            errors += entry_errors
            details.extend(entry_details)

        return {
            "status": "accepted",
            "processed": processed,
            "ignored": ignored,
            "errors": errors,
            "event_count": processed + ignored + errors,
            "details": details,
        }

    def _handle_entry(self, entry: Any) -> tuple[int, int, int, list[str]]:
        if not isinstance(entry, dict):
            return 0, 1, 0, ["Ignored malformed Facebook entry."]

        page_id = self._clean_text(entry.get("id"))
        page = self._find_page(page_id) if page_id else None
        details: list[str] = []
        processed = 0
        ignored = 0
        errors = 0

        messaging_events = entry.get("messaging") or []
        if isinstance(messaging_events, list):
            for event in messaging_events:
                outcome, detail = self._process_event(self._handle_messaging_event, page, page_id, entry, event)
                if outcome == "processed":
                    processed += 1
                elif outcome == "ignored":
                    ignored += 1
                else:
                    errors += 1
                details.append(detail)

        change_events = entry.get("changes") or []
        if isinstance(change_events, list):
            for change in change_events:
                outcome, detail = self._process_event(self._handle_change_event, page, page_id, entry, change)
                if outcome == "processed":
                    processed += 1
                elif outcome == "ignored":
                    ignored += 1
                else:
                    errors += 1
                details.append(detail)

        if processed == 0 and ignored == 0 and errors == 0:
            return 0, 1, 0, [f"Ignored Facebook entry for page {page_id or 'unknown'} with no supported events."]

        return processed, ignored, errors, details

    def _process_event(
        self,
        handler: Any,
        page: models.FacebookPageAutomation | None,
        page_id: str | None,
        entry: dict[str, Any],
        event: Any,
    ) -> tuple[str, str]:
        try:
            return handler(page, page_id, entry, event)
        except HTTPException as exc:
            self.db.rollback()
            return "error", f"Failed Facebook event for page {page_id or 'unknown'}: {exc.detail}"
        except Exception as exc:  # noqa: BLE001
            self.db.rollback()
            return "error", f"Failed Facebook event for page {page_id or 'unknown'}: {exc}"

    def _handle_messaging_event(
        self,
        page: models.FacebookPageAutomation | None,
        page_id: str | None,
        entry: dict[str, Any],
        event: Any,
    ) -> tuple[str, str]:
        if not isinstance(event, dict):
            return "ignored", f"Ignored malformed Messenger event for page {page_id or 'unknown'}."
        if page is None:
            return "ignored", f"Ignored Messenger event for unknown page {page_id or 'unknown'}."
        if not page.active or not page.automation_enabled or not page.reply_to_messages:
            return "ignored", f"Ignored Messenger event for page {page.page_id} because message automation is disabled."

        message = event.get("message") if isinstance(event.get("message"), dict) else None
        if message and bool(message.get("is_echo")):
            return "ignored", f"Ignored echo Messenger event for page {page.page_id}."

        sender_id = self._extract_actor_id(event.get("sender"))
        if not sender_id:
            return "ignored", f"Ignored Messenger event for page {page.page_id} without a sender id."
        if sender_id == page.page_id:
            return "ignored", f"Ignored self-authored Messenger event for page {page.page_id}."

        text, metadata = self._extract_messaging_content(event)
        if not text:
            return "ignored", f"Ignored Messenger event for page {page.page_id} because it had no text or supported fallback content."

        external_message_id = (
            self._clean_text(metadata.get("message_mid"))
            or self._clean_text(metadata.get("postback_mid"))
            or self._clean_text(event.get("mid"))
        )
        request_payload = MessageProcessRequest(
            brand_id=page.brand_id,
            channel="facebook_messenger",
            customer_external_id=sender_id,
            customer_language=page.default_language,
            conversation_external_id=f"facebook:{page.page_id}:{sender_id}",
            external_message_id=external_message_id,
            text=text,
            metadata={
                "source_platform": "facebook",
                "event_type": "messaging",
                "page_id": page.page_id,
                "entry_time": entry.get("time"),
                "sender_id": sender_id,
                "recipient_id": self._extract_actor_id(event.get("recipient")),
                "timestamp": event.get("timestamp"),
                "message": metadata,
                "raw_event": event,
            },
        )
        result = MessageProcessor(self.db).process(request_payload)
        return "processed", f"Processed Messenger event for page {page.page_id} into conversation {result.conversation_id}."

    def _handle_change_event(
        self,
        page: models.FacebookPageAutomation | None,
        page_id: str | None,
        entry: dict[str, Any],
        change: Any,
    ) -> tuple[str, str]:
        if not isinstance(change, dict):
            return "ignored", f"Ignored malformed Page change event for page {page_id or 'unknown'}."
        if page is None:
            return "ignored", f"Ignored Page change event for unknown page {page_id or 'unknown'}."
        if not page.active or not page.automation_enabled or not page.reply_to_comments:
            return "ignored", f"Ignored Page change event for page {page.page_id} because comment automation is disabled."

        field_name = self._clean_text(change.get("field"))
        value = change.get("value") if isinstance(change.get("value"), dict) else {}
        item_type = self._clean_text(value.get("item"))
        verb = self._clean_text(value.get("verb"))
        if field_name != "feed" or item_type != "comment" or verb not in {"add", "edited"}:
            return "ignored", f"Ignored unsupported Page change event for page {page.page_id}."

        author_id = self._extract_actor_id(value.get("from")) or self._clean_text(value.get("sender_id"))
        if author_id == page.page_id:
            return "ignored", f"Ignored self-authored comment event for page {page.page_id}."

        comment_id = self._clean_text(value.get("comment_id"))
        thread_id = self._clean_text(value.get("parent_id")) or comment_id or self._clean_text(value.get("post_id"))
        text = self._clean_text(value.get("message"))
        if not author_id or not thread_id or not text:
            return "ignored", f"Ignored incomplete comment event for page {page.page_id}."

        request_payload = MessageProcessRequest(
            brand_id=page.brand_id,
            channel="facebook_comment",
            customer_external_id=author_id,
            customer_name=self._clean_text((value.get("from") or {}).get("name")) if isinstance(value.get("from"), dict) else None,
            customer_language=page.default_language,
            conversation_external_id=f"facebook-comment:{page.page_id}:{thread_id}",
            external_message_id=comment_id,
            text=text,
            metadata={
                "source_platform": "facebook",
                "event_type": "comment",
                "page_id": page.page_id,
                "entry_time": entry.get("time"),
                "comment_id": comment_id,
                "thread_id": thread_id,
                "post_id": self._clean_text(value.get("post_id")),
                "parent_id": self._clean_text(value.get("parent_id")),
                "verb": verb,
                "field": field_name,
                "raw_change": change,
            },
        )
        result = MessageProcessor(self.db).process(request_payload)
        return "processed", f"Processed comment event for page {page.page_id} into conversation {result.conversation_id}."

    def _extract_messaging_content(self, event: dict[str, Any]) -> tuple[str, dict[str, Any]]:
        metadata: dict[str, Any] = {}

        message = event.get("message")
        if isinstance(message, dict):
            message_text = self._clean_text(message.get("text"))
            metadata["message_mid"] = self._clean_text(message.get("mid"))
            attachments = message.get("attachments") if isinstance(message.get("attachments"), list) else []
            if attachments:
                metadata["attachments"] = attachments
            quick_reply = message.get("quick_reply") if isinstance(message.get("quick_reply"), dict) else None
            if quick_reply:
                metadata["quick_reply_payload"] = self._clean_text(quick_reply.get("payload"))
            if message_text:
                return message_text, metadata
            if attachments:
                attachment_types = [self._clean_text(item.get("type")) or "attachment" for item in attachments if isinstance(item, dict)]
                summary = ", ".join(dict.fromkeys(attachment_types)) or "attachment"
                return f"[Facebook attachment received: {summary}]", metadata

        postback = event.get("postback")
        if isinstance(postback, dict):
            metadata["postback_mid"] = self._clean_text(postback.get("mid"))
            metadata["postback_title"] = self._clean_text(postback.get("title"))
            metadata["postback_payload"] = self._clean_text(postback.get("payload"))
            text = metadata["postback_title"] or metadata["postback_payload"] or "[Facebook postback received]"
            return text, metadata

        return "", metadata

    def _verify_signature_if_present(
        self,
        raw_body: bytes,
        signature_header: str | None,
        payload: dict[str, Any],
    ) -> None:
        if not signature_header:
            return
        if not signature_header.startswith("sha256="):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid Facebook signature header.")

        expected_signature = signature_header.split("=", 1)[1].strip()
        if not expected_signature:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing Facebook signature digest.")

        candidate_secrets = self._candidate_app_secrets(payload)
        if not candidate_secrets:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="No Facebook app secret is configured for this webhook payload.")

        for secret in candidate_secrets:
            digest = hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
            if hmac.compare_digest(digest, expected_signature):
                return

        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Facebook webhook signature verification failed.")

    def _candidate_app_secrets(self, payload: dict[str, Any]) -> list[str]:
        page_ids = []
        for entry in payload.get("entry", []):
            if isinstance(entry, dict):
                page_id = self._clean_text(entry.get("id"))
                if page_id:
                    page_ids.append(page_id)

        statement = select(models.FacebookPageAutomation.app_secret)
        if page_ids:
            statement = statement.where(models.FacebookPageAutomation.page_id.in_(page_ids))

        secrets = [
            secret
            for secret in self.db.scalars(statement.distinct())
            if isinstance(secret, str) and secret.strip()
        ]
        return secrets

    def _find_page(self, page_id: str) -> models.FacebookPageAutomation | None:
        return self.db.scalar(
            select(models.FacebookPageAutomation).where(models.FacebookPageAutomation.page_id == page_id)
        )

    @staticmethod
    def _extract_actor_id(value: Any) -> str | None:
        if isinstance(value, dict):
            return FacebookWebhookService._clean_text(value.get("id"))
        return None

    @staticmethod
    def _clean_text(value: Any) -> str | None:
        normalized = str(value or "").strip()
        return normalized or None
