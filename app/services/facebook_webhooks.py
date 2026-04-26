from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import json
from pathlib import PurePosixPath
from typing import Any
from urllib.parse import urlparse

from fastapi import HTTPException, status
import httpx
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app import models
from app.api.schemas.messages import MessageProcessRequest
from app.config import get_settings
from app.services.jobs import enqueue_job
from app.services.orchestrator import MessageProcessor
from app.services.storage import detect_attachment_type, save_upload_bytes


class FacebookMessengerDeliveryError(RuntimeError):
    """Raised when the Meta Messenger Send API rejects or fails a reply."""


PENDING_REVIEW_LABEL_NAME = "Pending Review"


class FacebookMessengerClient:
    graph_api_base_url = "https://graph.facebook.com/v25.0"

    def __init__(self, page_access_token: str, timeout_seconds: float = 10.0) -> None:
        self.page_access_token = page_access_token.strip()
        self.timeout_seconds = timeout_seconds

    def send_text_message(self, recipient_id: str, text: str) -> dict[str, Any]:
        cleaned_recipient_id = recipient_id.strip()
        cleaned_text = text.strip()
        if not self.page_access_token:
            raise FacebookMessengerDeliveryError("Facebook page access token is missing.")
        if not cleaned_recipient_id:
            raise FacebookMessengerDeliveryError("Messenger recipient id is missing.")
        if not cleaned_text:
            raise FacebookMessengerDeliveryError("Messenger reply text is empty.")

        try:
            response = httpx.post(
                f"{self.graph_api_base_url}/me/messages",
                params={"access_token": self.page_access_token},
                json={
                    "recipient": {"id": cleaned_recipient_id},
                    "messaging_type": "RESPONSE",
                    "message": {"text": cleaned_text},
                },
                timeout=self.timeout_seconds,
            )
        except httpx.HTTPError as exc:
            raise FacebookMessengerDeliveryError(f"Facebook Send API request failed: {exc}") from exc

        try:
            payload = response.json()
        except ValueError:
            payload = None

        if response.status_code >= 400:
            detail = self._extract_error_detail(payload) or response.text or f"HTTP {response.status_code}"
            raise FacebookMessengerDeliveryError(f"Facebook Send API rejected the reply: {detail}")

        if not isinstance(payload, dict):
            raise FacebookMessengerDeliveryError("Facebook Send API returned an invalid JSON response.")

        return payload

    def get_user_profile(self, recipient_id: str) -> dict[str, Any] | None:
        cleaned_recipient_id = recipient_id.strip()
        if not self.page_access_token or not cleaned_recipient_id:
            return None
        try:
            response = httpx.get(
                f"{self.graph_api_base_url}/{cleaned_recipient_id}",
                params={
                    "access_token": self.page_access_token,
                    "fields": "name,first_name,last_name,profile_pic",
                },
                timeout=self.timeout_seconds,
            )
        except httpx.HTTPError:
            return None
        if response.status_code >= 400:
            return None
        try:
            payload = response.json()
        except Exception:  # noqa: BLE001
            return None
        return payload if isinstance(payload, dict) else None

    def ensure_custom_label(self, page_id: str, label_name: str) -> str | None:
        normalized_name = label_name.strip()
        if not self.page_access_token or not page_id.strip() or not normalized_name:
            return None

        existing = self.list_custom_labels(page_id)
        for item in existing:
            if str(item.get("name") or "").strip().lower() == normalized_name.lower():
                label_id = str(item.get("id") or "").strip()
                if label_id:
                    return label_id

        try:
            response = httpx.post(
                f"{self.graph_api_base_url}/{page_id}/custom_labels",
                params={"access_token": self.page_access_token},
                data={"name": normalized_name},
                timeout=self.timeout_seconds,
            )
        except httpx.HTTPError:
            return None
        if response.status_code >= 400:
            return None
        try:
            payload = response.json()
        except ValueError:
            return None
        if not isinstance(payload, dict):
            return None
        return str(payload.get("id") or "").strip() or None

    def list_custom_labels(self, page_id: str) -> list[dict[str, Any]]:
        if not self.page_access_token or not page_id.strip():
            return []
        try:
            response = httpx.get(
                f"{self.graph_api_base_url}/{page_id}/custom_labels",
                params={"access_token": self.page_access_token},
                timeout=self.timeout_seconds,
            )
        except httpx.HTTPError:
            return []
        if response.status_code >= 400:
            return []
        try:
            payload = response.json()
        except ValueError:
            return []
        data = payload.get("data") if isinstance(payload, dict) else None
        return [item for item in data if isinstance(item, dict)] if isinstance(data, list) else []

    def associate_label(self, recipient_id: str, label_id: str) -> bool:
        if not self.page_access_token or not recipient_id.strip() or not label_id.strip():
            return False
        try:
            response = httpx.post(
                f"{self.graph_api_base_url}/{recipient_id}/custom_labels",
                params={
                    "access_token": self.page_access_token,
                    "custom_label_id": label_id,
                },
                timeout=self.timeout_seconds,
            )
        except httpx.HTTPError:
            return False
        return response.status_code < 400

    def remove_label(self, recipient_id: str, label_id: str) -> bool:
        if not self.page_access_token or not recipient_id.strip() or not label_id.strip():
            return False
        try:
            response = httpx.delete(
                f"{self.graph_api_base_url}/{recipient_id}/custom_labels",
                params={
                    "access_token": self.page_access_token,
                    "custom_label_id": label_id,
                },
                timeout=self.timeout_seconds,
            )
        except httpx.HTTPError:
            return False
        return response.status_code < 400

    @staticmethod
    def _extract_error_detail(payload: Any) -> str | None:
        if not isinstance(payload, dict):
            return None

        error = payload.get("error")
        if isinstance(error, dict):
            message = error.get("message")
            code = error.get("code")
            subcode = error.get("error_subcode")
            parts = [str(item).strip() for item in (message, code, subcode) if str(item).strip()]
            return " | ".join(parts) if parts else None

        return None


class FacebookWebhookService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.settings = get_settings()

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

        referral = self._extract_referral_metadata(event)

        external_message_id = (
            self._clean_text(((event.get("message") or {}) if isinstance(event.get("message"), dict) else {}).get("mid"))
            or self._clean_text(((event.get("postback") or {}) if isinstance(event.get("postback"), dict) else {}).get("mid"))
            or self._clean_text(event.get("mid"))
        )
        skip_attachment_capture = bool(
            external_message_id
            and self.db.scalar(
                select(models.Message.id).where(
                    models.Message.brand_id == page.brand_id,
                    models.Message.external_message_id == external_message_id,
                )
            )
        )
        text, metadata, attachment_ids = self._extract_messaging_content(
            page,
            event,
            capture_attachments=not skip_attachment_capture,
        )
        customer_name = self._resolve_customer_name(page, sender_id) if text else None
        if not text and not attachment_ids:
            return "ignored", f"Ignored Messenger event for page {page.page_id} because it had no text or supported fallback content."

        external_message_id = (
            self._clean_text(metadata.get("message_mid"))
            or self._clean_text(metadata.get("postback_mid"))
            or external_message_id
        )
        request_payload = MessageProcessRequest(
            brand_id=page.brand_id,
            channel="facebook_messenger",
            customer_external_id=sender_id,
            customer_name=customer_name,
            customer_language=page.default_language,
            conversation_external_id=f"facebook:{page.page_id}:{sender_id}",
            external_message_id=external_message_id,
            text=text,
            attachment_ids=attachment_ids,
            metadata={
                "ad_id": referral.get("ad_id"),
                "referral": referral,
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
        if self._should_batch_messenger_messages():
            job = self._enqueue_or_merge_messenger_job(page, request_payload)
            detail = (
                f"Queued Messenger event for page {page.page_id} as job {job.id}. "
                "The reply will be generated after the short typing window closes."
            )
            return "processed", detail
        if self.settings.facebook_webhook_async_enabled:
            queued_payload = request_payload.model_copy(update={"process_async": True})
            job = enqueue_job(self.db, "process_message", queued_payload.model_dump(), page.brand_id)
            detail = (
                f"Queued Messenger event for page {page.page_id} as job {job.id}. "
                "The background runner will generate and deliver the reply."
            )
            return "processed", detail

        result = MessageProcessor(self.db).process(request_payload)
        delivery_state = self._deliver_messenger_reply(page=page, recipient_id=sender_id, result=result)
        self._sync_pending_review_label_for_result(result)
        if delivery_state == "sent":
            detail = (
                f"Processed Messenger event for page {page.page_id} into conversation "
                f"{result.conversation_id} and sent the reply through Meta."
            )
        elif delivery_state == "already_sent":
            detail = (
                f"Processed Messenger event for page {page.page_id} into conversation "
                f"{result.conversation_id}; the Messenger reply was already delivered."
            )
        else:
            detail = f"Processed Messenger event for page {page.page_id} into conversation {result.conversation_id}."
        return "processed", detail

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
        if self.settings.facebook_webhook_async_enabled:
            queued_payload = request_payload.model_copy(update={"process_async": True})
            job = enqueue_job(self.db, "process_message", queued_payload.model_dump(), page.brand_id)
            return "processed", f"Queued comment event for page {page.page_id} as job {job.id}."

        result = MessageProcessor(self.db).process(request_payload)
        return "processed", f"Processed comment event for page {page.page_id} into conversation {result.conversation_id}."

    def _extract_messaging_content(
        self,
        page: models.FacebookPageAutomation,
        event: dict[str, Any],
        *,
        capture_attachments: bool = True,
    ) -> tuple[str, dict[str, Any], list[int]]:
        metadata: dict[str, Any] = {}
        attachment_ids: list[int] = []

        message = event.get("message")
        if isinstance(message, dict):
            message_text = self._clean_text(message.get("text"))
            metadata["message_mid"] = self._clean_text(message.get("mid"))
            reply_to = message.get("reply_to") if isinstance(message.get("reply_to"), dict) else None
            if reply_to:
                metadata["reply_to"] = self._normalize_reply_target(reply_to)
            referral = self._extract_referral_metadata(message)
            if referral:
                metadata["referral"] = referral
                metadata["ad_id"] = referral.get("ad_id")
            attachments = message.get("attachments") if isinstance(message.get("attachments"), list) else []
            if attachments:
                metadata["attachments"] = attachments
                attachment_ids, attachment_errors = (
                    self._capture_supported_attachments(page, attachments)
                    if capture_attachments
                    else ([], [])
                )
                if attachment_ids:
                    metadata["captured_attachment_ids"] = attachment_ids
                if attachment_errors:
                    metadata["attachment_download_errors"] = attachment_errors
            quick_reply = message.get("quick_reply") if isinstance(message.get("quick_reply"), dict) else None
            if quick_reply:
                metadata["quick_reply_payload"] = self._clean_text(quick_reply.get("payload"))
            if message_text:
                return message_text, metadata, attachment_ids
            if attachment_ids:
                return "", metadata, attachment_ids
            if attachments:
                attachment_types = [self._clean_text(item.get("type")) or "attachment" for item in attachments if isinstance(item, dict)]
                summary = ", ".join(dict.fromkeys(attachment_types)) or "attachment"
                return f"[Facebook attachment received: {summary}]", metadata, attachment_ids

        postback = event.get("postback")
        if isinstance(postback, dict):
            metadata["postback_mid"] = self._clean_text(postback.get("mid"))
            metadata["postback_title"] = self._clean_text(postback.get("title"))
            metadata["postback_payload"] = self._clean_text(postback.get("payload"))
            referral = self._extract_referral_metadata(postback)
            if referral:
                metadata["referral"] = referral
                metadata["ad_id"] = referral.get("ad_id")
            text = metadata["postback_title"] or metadata["postback_payload"] or "[Facebook postback received]"
            return text, metadata, attachment_ids

        return "", metadata, attachment_ids

    def _capture_supported_attachments(
        self,
        page: models.FacebookPageAutomation,
        attachments: list[Any],
    ) -> tuple[list[int], list[str]]:
        captured_ids: list[int] = []
        errors: list[str] = []

        for index, attachment in enumerate(attachments):
            if not isinstance(attachment, dict):
                continue
            attachment_type = self._clean_text(attachment.get("type")) or "attachment"
            if attachment_type not in {"image", "audio"}:
                continue

            try:
                captured_ids.append(self._store_supported_attachment(page, attachment, attachment_type, index))
            except Exception as exc:  # noqa: BLE001
                errors.append(f"{attachment_type}:{exc}")

        return captured_ids, errors

    def _store_supported_attachment(
        self,
        page: models.FacebookPageAutomation,
        attachment: dict[str, Any],
        attachment_type: str,
        index: int,
    ) -> int:
        payload = attachment.get("payload") if isinstance(attachment.get("payload"), dict) else {}
        source_url = self._clean_text(payload.get("url"))
        if not source_url:
            raise RuntimeError("attachment URL missing")

        response = self._download_attachment(source_url, page.page_access_token)
        mime_type = self._clean_content_type(response.headers.get("content-type")) or self._default_mime_type(attachment_type)
        filename = self._attachment_filename(source_url, mime_type, attachment_type, index)
        storage_path, stored_mime_type = save_upload_bytes(page.brand_id, filename, response.content, mime_type)
        stored_attachment_type = attachment_type if attachment_type in {"audio", "image"} else detect_attachment_type(stored_mime_type, filename)

        row = models.Attachment(
            brand_id=page.brand_id,
            attachment_type=stored_attachment_type,
            mime_type=stored_mime_type,
            original_filename=filename,
            storage_path=storage_path,
            metadata_json={
                "source_platform": "facebook",
                "facebook_attachment_type": attachment_type,
                "facebook_attachment_id": self._clean_text(payload.get("attachment_id")),
                "facebook_title": self._clean_text(payload.get("title")),
            },
        )
        self.db.add(row)
        self.db.flush()
        return row.id

    def _download_attachment(self, source_url: str, page_access_token: str) -> httpx.Response:
        try:
            response = httpx.get(source_url, timeout=20.0, follow_redirects=True)
        except httpx.HTTPError as exc:
            raise RuntimeError(f"attachment download failed: {exc}") from exc

        if response.status_code in {401, 403} and page_access_token:
            try:
                response = httpx.get(
                    source_url,
                    params={"access_token": page_access_token},
                    timeout=20.0,
                    follow_redirects=True,
                )
            except httpx.HTTPError as exc:
                raise RuntimeError(f"attachment download failed: {exc}") from exc

        if response.status_code >= 400:
            raise RuntimeError(f"attachment download returned HTTP {response.status_code}")

        return response

    def _attachment_filename(self, source_url: str, mime_type: str, attachment_type: str, index: int) -> str:
        parsed = urlparse(source_url)
        candidate = PurePosixPath(parsed.path or "").name
        suffix = PurePosixPath(candidate).suffix
        if not suffix:
            suffix = self._mime_suffix(mime_type)
            candidate = f"facebook-{attachment_type}-{index + 1}{suffix}"
        return candidate or f"facebook-{attachment_type}-{index + 1}{suffix or '.bin'}"

    @staticmethod
    def _clean_content_type(value: Any) -> str | None:
        normalized = str(value or "").strip()
        if not normalized:
            return None
        return normalized.split(";", 1)[0].strip() or None

    @staticmethod
    def _default_mime_type(attachment_type: str) -> str:
        if attachment_type == "image":
            return "image/jpeg"
        if attachment_type == "audio":
            return "audio/mpeg"
        return "application/octet-stream"

    @staticmethod
    def _mime_suffix(mime_type: str) -> str:
        mapping = {
            "image/jpeg": ".jpg",
            "image/png": ".png",
            "image/webp": ".webp",
            "image/gif": ".gif",
            "audio/mpeg": ".mp3",
            "audio/mp3": ".mp3",
            "audio/ogg": ".ogg",
            "audio/mp4": ".m4a",
            "video/mp4": ".m4a",
            "audio/wav": ".wav",
        }
        return mapping.get(mime_type, ".bin")

    def _resolve_customer_name(self, page: models.FacebookPageAutomation, sender_id: str) -> str | None:
        existing_customer = self.db.scalar(
            select(models.Customer.display_name).where(
                models.Customer.brand_id == page.brand_id,
                models.Customer.external_id == sender_id,
            )
        )
        cached_name = self._clean_text(existing_customer)
        if cached_name:
            return cached_name

        profile = FacebookMessengerClient(page.page_access_token).get_user_profile(sender_id)
        if not isinstance(profile, dict):
            return None
        return (
            self._clean_text(profile.get("name"))
            or " ".join(
                part for part in [
                    self._clean_text(profile.get("first_name")),
                    self._clean_text(profile.get("last_name")),
                ] if part
            ).strip()
            or None
        )

    def _extract_referral_metadata(self, source: Any) -> dict[str, Any]:
        payload = source if isinstance(source, dict) else {}
        referral = payload.get("referral") if isinstance(payload.get("referral"), dict) else {}
        ads_context = referral.get("ads_context_data") if isinstance(referral.get("ads_context_data"), dict) else {}
        result = {
            "ref": self._clean_text(referral.get("ref")),
            "source": self._clean_text(referral.get("source")),
            "type": self._clean_text(referral.get("type")),
            "ad_id": self._clean_text(referral.get("ad_id")) or self._clean_text(ads_context.get("ad_id")),
            "post_id": self._clean_text(referral.get("post_id")) or self._clean_text(ads_context.get("post_id")),
            "ad_title": self._clean_text(ads_context.get("ad_title")),
            "photo_url": self._clean_text(ads_context.get("photo_url")),
            "video_url": self._clean_text(ads_context.get("video_url")),
            "referer_uri": self._clean_text(referral.get("referer_uri")),
        }
        return {key: value for key, value in result.items() if value}

    def _deliver_messenger_reply(
        self,
        *,
        page: models.FacebookPageAutomation,
        recipient_id: str,
        result: Any,
    ) -> str:
        outbound_message_id = getattr(result, "outbound_message_id", None)
        if not outbound_message_id:
            return "no_reply"

        outbound_row = self.db.execute(
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

        existing_delivery_id = self._clean_text(outbound_row.external_message_id)
        if existing_delivery_id:
            return "already_sent"

        reply_text = (getattr(result, "reply_text", None) or outbound_row.text or "").strip()
        if not reply_text:
            return "no_reply"

        try:
            delivery = FacebookMessengerClient(page.page_access_token).send_text_message(recipient_id=recipient_id, text=reply_text)
        except FacebookMessengerDeliveryError as exc:
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc

        sent_message_id = (
            self._clean_text(delivery.get("message_id")) or f"facebook-sent:{outbound_message_id}"
        )
        update_result = self.db.execute(
            update(models.Message)
            .where(models.Message.id == outbound_message_id)
            .values(external_message_id=sent_message_id)
            .execution_options(synchronize_session=False)
        )
        if update_result.rowcount == 0:
            persisted_delivery_id = self.db.scalar(
                select(models.Message.external_message_id).where(models.Message.id == outbound_message_id)
            )
            if self._clean_text(persisted_delivery_id):
                self.db.rollback()
                return "already_sent"
            self.db.rollback()
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Generated reply {outbound_message_id} could not be marked as delivered.",
            )
        self.db.commit()
        return "sent"

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

    def _should_batch_messenger_messages(self) -> bool:
        return self.settings.facebook_message_batching_enabled and self.settings.facebook_message_batch_window_seconds > 0

    def _enqueue_or_merge_messenger_job(
        self,
        page: models.FacebookPageAutomation,
        request_payload: MessageProcessRequest,
    ) -> models.Job:
        available_at = datetime.now(timezone.utc) + timedelta(seconds=self.settings.facebook_message_batch_window_seconds)
        pending_job = self._find_pending_messenger_batch_job(page.brand_id, request_payload.conversation_external_id)
        payload_dict = request_payload.model_dump()
        payload_dict["process_async"] = True
        payload_dict["metadata"] = self._build_batched_metadata(payload_dict)

        if pending_job is None:
            return enqueue_job(
                self.db,
                "process_message",
                payload_dict,
                page.brand_id,
                available_at=available_at,
            )

        pending_payload = dict(pending_job.payload_json or {})
        merged_payload = self._merge_batched_process_payload(pending_payload, payload_dict)
        pending_job.payload_json = merged_payload
        pending_job.available_at = available_at
        pending_job.last_error = None
        self.db.add(pending_job)
        self.db.commit()
        self.db.refresh(pending_job)
        return pending_job

    def _find_pending_messenger_batch_job(self, brand_id: int, conversation_external_id: str) -> models.Job | None:
        candidate_jobs = list(
            self.db.scalars(
                select(models.Job)
                .where(models.Job.brand_id == brand_id, models.Job.kind == "process_message", models.Job.status == "pending")
                .order_by(models.Job.created_at.desc())
            )
        )
        for job in candidate_jobs:
            payload = job.payload_json or {}
            if payload.get("channel") != "facebook_messenger":
                continue
            if str(payload.get("conversation_external_id") or "").strip() != conversation_external_id.strip():
                continue
            metadata = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}
            if not metadata.get("batching_window_seconds"):
                continue
            return job
        return None

    def _build_batched_metadata(self, payload: dict[str, Any]) -> dict[str, Any]:
        metadata = dict(payload.get("metadata") or {})
        first_text = str(payload.get("text") or "").strip()
        message_mid = str(payload.get("external_message_id") or "").strip()
        metadata.update(
            {
                "batched_messages": [
                    {
                        "external_message_id": message_mid,
                        "text": first_text,
                        "attachment_ids": list(payload.get("attachment_ids") or []),
                        "timestamp": metadata.get("timestamp"),
                    }
                ],
                "batched_external_message_ids": [message_mid] if message_mid else [],
                "batching_window_seconds": self.settings.facebook_message_batch_window_seconds,
            }
        )
        return metadata

    def _merge_batched_process_payload(self, existing: dict[str, Any], incoming: dict[str, Any]) -> dict[str, Any]:
        merged = dict(existing)
        existing_metadata = dict(existing.get("metadata") or {})
        incoming_metadata = dict(incoming.get("metadata") or {})
        existing_ids = [
            str(item).strip()
            for item in existing_metadata.get("batched_external_message_ids", [])
            if str(item).strip()
        ]
        incoming_external_message_id = str(incoming.get("external_message_id") or "").strip()
        if incoming_external_message_id and incoming_external_message_id in existing_ids:
            return merged

        existing_text = str(existing.get("text") or "").strip()
        incoming_text = str(incoming.get("text") or "").strip()
        if incoming_text:
            merged["text"] = "\n".join(part for part in [existing_text, incoming_text] if part)

        merged["attachment_ids"] = list(
            dict.fromkeys([*(existing.get("attachment_ids") or []), *(incoming.get("attachment_ids") or [])])
        )
        merged["customer_name"] = incoming.get("customer_name") or existing.get("customer_name")
        merged["customer_language"] = incoming.get("customer_language") or existing.get("customer_language")
        merged["external_message_id"] = incoming.get("external_message_id") or existing.get("external_message_id")
        merged["process_async"] = True

        merged_messages = list(existing_metadata.get("batched_messages") or [])
        merged_messages.append(
            {
                "external_message_id": incoming_external_message_id,
                "text": incoming_text,
                "attachment_ids": list(incoming.get("attachment_ids") or []),
                "timestamp": incoming_metadata.get("timestamp"),
            }
        )
        merged_metadata = self._merge_metadata(existing_metadata, incoming_metadata)
        merged_metadata["batched_messages"] = merged_messages
        merged_metadata["batched_external_message_ids"] = [
            *existing_ids,
            *([incoming_external_message_id] if incoming_external_message_id else []),
        ]
        merged_metadata["batching_window_seconds"] = self.settings.facebook_message_batch_window_seconds
        merged["metadata"] = merged_metadata
        return merged

    def _merge_metadata(self, existing: dict[str, Any], incoming: dict[str, Any]) -> dict[str, Any]:
        merged = dict(existing)
        for key, value in incoming.items():
            if isinstance(value, dict):
                nested_existing = merged.get(key) if isinstance(merged.get(key), dict) else {}
                if value:
                    merged[key] = self._merge_metadata(dict(nested_existing), value)
                elif key not in merged:
                    merged[key] = {}
                continue
            if isinstance(value, list):
                if value or key not in merged:
                    merged[key] = value
                continue
            if value is None or (isinstance(value, str) and not value.strip()):
                continue
            merged[key] = value
        return merged

    def _normalize_reply_target(self, payload: dict[str, Any]) -> dict[str, Any]:
        target = {
            "mid": self._clean_text(payload.get("mid"))
            or self._clean_text(payload.get("message_id"))
            or self._clean_text(payload.get("reply_to_mid")),
            "story": self._clean_text(payload.get("story")),
        }
        message = payload.get("message") if isinstance(payload.get("message"), dict) else None
        if message:
            target["mid"] = target.get("mid") or self._clean_text(message.get("mid"))
            target["text"] = self._clean_text(message.get("text"))
        return {key: value for key, value in target.items() if value}

    def _find_page(self, page_id: str) -> models.FacebookPageAutomation | None:
        return self.db.scalar(
            select(models.FacebookPageAutomation).where(models.FacebookPageAutomation.page_id == page_id)
        )

    def _sync_pending_review_label_for_result(self, result: Any) -> None:
        conversation_id = getattr(result, "conversation_id", None)
        if not conversation_id:
            return
        conversation = self.db.get(models.Conversation, conversation_id)
        if conversation is None:
            return
        sync_pending_review_label(self.db, conversation, getattr(result, "status", None) == "handoff")

    @staticmethod
    def _extract_actor_id(value: Any) -> str | None:
        if isinstance(value, dict):
            return FacebookWebhookService._clean_text(value.get("id"))
        return None

    @staticmethod
    def _clean_text(value: Any) -> str | None:
        normalized = str(value or "").strip()
        return normalized or None


def sync_pending_review_label(db: Session, conversation: models.Conversation, enabled: bool) -> bool:
    if conversation.channel != "facebook_messenger":
        return False
    metadata = conversation.metadata_json if isinstance(conversation.metadata_json, dict) else {}
    page_id = str(metadata.get("page_id") or "").strip()
    sender_id = str(metadata.get("sender_id") or "").strip()
    if not page_id or not sender_id:
        return False

    page = db.scalar(select(models.FacebookPageAutomation).where(models.FacebookPageAutomation.page_id == page_id))
    if page is None or not page.page_access_token:
        return False

    client = FacebookMessengerClient(page.page_access_token)
    known_labels = metadata.get("labels") if isinstance(metadata.get("labels"), dict) else {}
    label_id = str(known_labels.get("pending_review") or "").strip() or None
    if enabled:
        label_id = client.ensure_custom_label(page.page_id, PENDING_REVIEW_LABEL_NAME)
        if not label_id:
            return False
    elif not label_id:
        for item in client.list_custom_labels(page.page_id):
            if str(item.get("name") or "").strip().lower() == PENDING_REVIEW_LABEL_NAME.lower():
                candidate = str(item.get("id") or "").strip()
                if candidate:
                    label_id = candidate
                    break
        if not label_id:
            return False

    changed = client.associate_label(sender_id, label_id) if enabled else client.remove_label(sender_id, label_id)
    if changed:
        next_metadata = dict(metadata)
        label_state = dict(next_metadata.get("labels") or {})
        if enabled:
            label_state["pending_review"] = label_id
        else:
            label_state.pop("pending_review", None)
        next_metadata["labels"] = label_state
        conversation.metadata_json = next_metadata
        db.add(conversation)
        db.commit()
        db.refresh(conversation)
    return changed
