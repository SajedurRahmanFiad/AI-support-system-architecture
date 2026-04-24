from __future__ import annotations

from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app import models
from app.api.schemas.messages import MessageProcessRequest, MessageProcessResponse
from app.config import get_settings
from app.services import knowledge, memory, moderation
from app.services.brand_service import get_brand_or_404
from app.services.llm.base import AttachmentInsight
from app.services.llm.factory import build_llm_provider
from app.services.speech import build_speech_provider, build_unclear_audio_reply
from app.services.storage import read_file_bytes


class MessageProcessor:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.settings = get_settings()
        self.provider = build_llm_provider()
        self.speech_provider = build_speech_provider()

    def process(self, payload: MessageProcessRequest) -> MessageProcessResponse:
        brand = get_brand_or_404(self.db, payload.brand_id)
        if not brand.active:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Brand is inactive.")

        duplicate = None
        if payload.external_message_id:
            duplicate = self.db.scalar(
                select(models.Message).where(
                    models.Message.brand_id == payload.brand_id,
                    models.Message.external_message_id == payload.external_message_id,
                )
            )
        if duplicate:
            duplicate_reply = self.db.scalar(
                select(models.Message)
                .where(
                    models.Message.conversation_id == duplicate.conversation_id,
                    models.Message.role == "assistant",
                    models.Message.id > duplicate.id,
                )
                .order_by(models.Message.id.asc())
            )
            return MessageProcessResponse(
                status=duplicate.status,
                conversation_id=duplicate.conversation_id,
                customer_id=duplicate.customer_id,
                inbound_message_id=duplicate.id,
                outbound_message_id=duplicate_reply.id if duplicate_reply else None,
                reply_text=duplicate_reply.text if duplicate_reply else None,
                confidence=duplicate_reply.confidence if duplicate_reply else None,
                handoff_reason=duplicate_reply.handoff_reason if duplicate_reply else duplicate.handoff_reason,
                flags=list(duplicate_reply.flags_json or duplicate.flags_json or []),
                used_sources=list(duplicate_reply.used_sources_json or []),
            )

        customer = self._get_or_create_customer(brand.id, payload)
        conversation = self._get_or_create_conversation(brand.id, customer.id, payload)

        inbound_message = models.Message(
            brand_id=brand.id,
            conversation_id=conversation.id,
            customer_id=customer.id,
            external_message_id=payload.external_message_id,
            role="customer",
            source=payload.channel,
            text=payload.text.strip(),
            status="received",
        )
        self.db.add(inbound_message)
        self.db.flush()

        attachments = self._bind_attachments(payload.attachment_ids, brand.id, conversation.id, customer.id, inbound_message.id)
        attachment_insights = self._prepare_attachment_insights(
            attachments=attachments,
            preferred_language=customer.language or brand.default_language,
        )
        inferred_language = next(
            (item.detected_language for item in attachment_insights if item.detected_language),
            None,
        )
        if inferred_language and not customer.language:
            customer.language = inferred_language
            self.db.add(customer)

        unclear_audio = self._find_unclear_audio_insight(attachment_insights)

        product_match = self._recognize_product_images(brand.id, attachments, payload.text)
        if product_match and product_match.get("matched"):
            attachment_insights.append(
                AttachmentInsight(
                    attachment_id=product_match.get("product_image_id", 0),
                    attachment_type="product_match",
                    summary=(
                        f"Recognized product match: {product_match['product_name']} "
                        f"(category: {product_match.get('category', 'general')}, "
                        f"confidence: {product_match.get('confidence', 0.0):.2f})."
                    ),
                    extracted_text=product_match.get("visual_summary"),
                )
            )

        hydrated_brand = self.db.scalar(
            select(models.Brand)
            .options(joinedload(models.Brand.rules), joinedload(models.Brand.style_examples))
            .where(models.Brand.id == brand.id)
        ) or brand
        brand_context = memory.build_brand_context(hydrated_brand)
        history = memory.fetch_recent_history(self.db, conversation.id)[:-1]
        customer_snapshot = memory.build_customer_snapshot(customer)

        moderation_text = " ".join(
            [payload.text]
            + [item.summary for item in attachment_insights]
            + [item.transcript or "" for item in attachment_insights]
            + [item.translated_text or "" for item in attachment_insights]
            + [item.extracted_text or "" for item in attachment_insights]
        ).strip()
        risk = moderation.inspect_customer_message(moderation_text, hydrated_brand.rules)
        if conversation.owner_type == "human":
            risk.force_handoff = True
            risk.reason = risk.reason or "Conversation is already assigned to a human."
            risk.flags.append("conversation-owned-by-human")

        if unclear_audio and not payload.text.strip():
            decision_status = "clarify"
            confidence = unclear_audio.analysis_confidence
            handoff_reason = unclear_audio.clarification_reason
            reply_text = build_unclear_audio_reply(customer.language or brand.default_language)
            customer_updates = {
                "language": unclear_audio.detected_language or customer.language or brand.default_language,
            }
            flags = list(dict.fromkeys(risk.flags + ["audio-needs-clarification"]))
            used_sources = [
                {
                    "type": "audio_transcription",
                    "provider": self.speech_provider.provider_name,
                    "language": unclear_audio.detected_language,
                    "confidence": unclear_audio.analysis_confidence,
                }
            ]
            token_usage = {}
            inbound_message.status = "clarify"
            inbound_message.flags_json = flags
            inbound_message.handoff_reason = handoff_reason
            conversation.status = "open"
            conversation.owner_type = "ai"
            now = datetime.now(timezone.utc)
            conversation.last_message_at = now
            customer.last_seen_at = now
            outbound_message = models.Message(
                brand_id=brand.id,
                conversation_id=conversation.id,
                customer_id=customer.id,
                role="assistant",
                source=self.speech_provider.provider_name,
                text=reply_text,
                status=decision_status,
                confidence=confidence,
                handoff_reason=handoff_reason,
                used_sources_json=used_sources,
                flags_json=flags,
                token_usage_json=token_usage,
            )
            self.db.add(outbound_message)
            self.db.flush()
            memory.apply_customer_updates(self.db, customer, customer_updates)
            audit = models.AuditLog(
                brand_id=brand.id,
                conversation_id=conversation.id,
                message_id=outbound_message.id,
                event_type="reply_generated",
                request_json=payload.model_dump(),
                response_json={
                    "status": decision_status,
                    "reply_text": reply_text,
                    "confidence": confidence,
                    "handoff_reason": handoff_reason,
                    "flags": flags,
                    "used_sources": used_sources,
                },
            )
            self.db.add_all([customer, conversation, inbound_message, outbound_message, audit])
            self.db.commit()
            return MessageProcessResponse(
                status=decision_status,
                conversation_id=conversation.id,
                customer_id=customer.id,
                inbound_message_id=inbound_message.id,
                outbound_message_id=outbound_message.id,
                reply_text=reply_text,
                confidence=confidence,
                handoff_reason=handoff_reason,
                flags=flags,
                used_sources=used_sources,
                customer_updates=customer_updates,
            )

        knowledge_hits = knowledge.search_knowledge(
            self.db,
            self.provider,
            brand.id,
            moderation_text or payload.text,
        )

        # If product was recognized, enhance search with product name
        if product_match and product_match.get("matched"):
            product_name = product_match["product_name"]
            aliases = product_match.get("metadata", {}).get("aliases") or []
            alias_text = " ".join(str(item) for item in aliases[:5])
            # Search for product-specific knowledge
            product_knowledge = knowledge.search_knowledge(
                self.db,
                self.provider,
                brand.id,
                f"{product_name} {alias_text} {payload.text}".strip(),
            )
            # Combine and deduplicate knowledge hits
            all_hits = knowledge_hits + product_knowledge
            # Remove duplicates based on chunk_id
            seen_chunks = set()
            unique_hits = []
            for hit in all_hits:
                if hit.chunk_id not in seen_chunks:
                    seen_chunks.add(hit.chunk_id)
                    unique_hits.append(hit)
            knowledge_hits = unique_hits[:self.settings.knowledge_top_k]

        assign_human_owner = False

        if risk.force_handoff:
            decision_status = "handoff"
            assign_human_owner = True
            confidence = 0.99
            handoff_reason = risk.reason or "Human review required."
            reply_text = hydrated_brand.fallback_handoff_message
            customer_updates: dict = {}
            flags = list(risk.flags)
            used_sources: list[dict] = []
            token_usage: dict = {}
        else:
            try:
                decision = self.provider.generate_reply(
                    brand=brand_context,
                    customer=customer_snapshot,
                    history=history,
                    incoming_text=payload.text,
                    knowledge=knowledge_hits,
                    attachment_insights=attachment_insights,
                )
            except Exception as exc:
                fallback_reply_text, fallback_sources = self._build_llm_failure_fallback_reply(knowledge_hits)
                if fallback_reply_text:
                    decision = None
                    decision_status = "send"
                    assign_human_owner = False
                    confidence = max(self.settings.handoff_confidence_threshold, 0.56)
                    handoff_reason = None
                    customer_updates = {}
                    flags = list(dict.fromkeys(risk.flags + ["llm-error", "knowledge-fallback"]))
                    used_sources = fallback_sources
                    token_usage = {}
                    reply_text = fallback_reply_text
                else:
                    # If LLM fails and we do not have a strong knowledge-backed fallback, handoff.
                    decision = None
                    decision_status = "handoff"
                    assign_human_owner = False
                    confidence = 0.0
                    handoff_reason = f"LLM service error: {exc}"
                    customer_updates = {}
                    flags = list(dict.fromkeys(risk.flags + ["llm-error"]))
                    used_sources = []
                    token_usage = {}
                    reply_text = hydrated_brand.fallback_handoff_message
            else:
                decision_status = decision.status
                assign_human_owner = decision_status == "handoff"
                confidence = decision.confidence
                handoff_reason = decision.handoff_reason
                customer_updates = decision.customer_updates
                flags = list(dict.fromkeys(risk.flags + decision.flags))
                used_sources = [
                    {
                        "chunk_id": item.chunk_id,
                        "document_id": item.document_id,
                        "title": item.title,
                        "score": item.score,
                    }
                    for item in knowledge_hits
                    if not decision.used_knowledge_ids or item.chunk_id in decision.used_knowledge_ids
                ]
                token_usage = decision.token_usage

                if decision_status != "handoff" and confidence < self.settings.handoff_confidence_threshold:
                    decision_status = "handoff"
                    assign_human_owner = False
                    handoff_reason = handoff_reason or "Low confidence reply needs human review."

                if decision_status == "handoff":
                    reply_text = hydrated_brand.fallback_handoff_message
                else:
                    reply_text = decision.reply_text.strip() or hydrated_brand.fallback_handoff_message

        if product_match and product_match.get("matched"):
            flags = list(dict.fromkeys(flags + [f"product-match:{product_match['product_name']}"]))
            used_sources.append(
                {
                    "type": "product_image_match",
                    "product_name": product_match["product_name"],
                    "category": product_match.get("category"),
                    "confidence": product_match.get("confidence"),
                    "product_image_id": product_match.get("product_image_id"),
                }
            )

        for insight in attachment_insights:
            if insight.attachment_type == "audio" and (insight.transcript or insight.detected_language):
                flags = list(dict.fromkeys(flags + ["audio-transcribed"]))
                used_sources.append(
                    {
                        "type": "audio_transcription",
                        "provider": self.speech_provider.provider_name,
                        "language": insight.detected_language,
                        "confidence": insight.analysis_confidence,
                    }
                )
                break

        inbound_message.status = "processed" if decision_status != "handoff" else "handoff"
        inbound_message.flags_json = flags
        inbound_message.handoff_reason = handoff_reason

        if decision_status == "handoff":
            conversation.status = "handoff"
            conversation.owner_type = "human" if assign_human_owner else "ai"
            if not assign_human_owner:
                conversation.owner_name = None
        else:
            conversation.status = "open"
            conversation.owner_type = "ai"
            conversation.owner_name = None

        now = datetime.now(timezone.utc)
        conversation.last_message_at = now
        customer.last_seen_at = now

        outbound_message = models.Message(
            brand_id=brand.id,
            conversation_id=conversation.id,
            customer_id=customer.id,
            role="assistant",
            source=self.provider.provider_name,
            text=reply_text,
            status=decision_status,
            confidence=confidence,
            handoff_reason=handoff_reason,
            used_sources_json=used_sources,
            flags_json=flags,
            token_usage_json=token_usage,
        )
        self.db.add(outbound_message)
        self.db.flush()

        memory.apply_customer_updates(self.db, customer, customer_updates)
        memory.maybe_refresh_summary(self.db, self.provider, brand_context, customer, conversation)

        audit = models.AuditLog(
            brand_id=brand.id,
            conversation_id=conversation.id,
            message_id=outbound_message.id,
            event_type="reply_generated",
            request_json=payload.model_dump(),
            response_json={
                "status": decision_status,
                "reply_text": reply_text,
                "confidence": confidence,
                "handoff_reason": handoff_reason,
                "flags": flags,
                "used_sources": used_sources,
            },
        )
        self.db.add_all([customer, conversation, inbound_message, outbound_message, audit])
        self.db.commit()

        return MessageProcessResponse(
            status=decision_status,
            conversation_id=conversation.id,
            customer_id=customer.id,
            inbound_message_id=inbound_message.id,
            outbound_message_id=outbound_message.id,
            reply_text=reply_text,
            confidence=confidence,
            handoff_reason=handoff_reason,
            flags=flags,
            used_sources=used_sources,
            customer_updates=customer_updates,
        )

    def _get_or_create_customer(self, brand_id: int, payload: MessageProcessRequest) -> models.Customer:
        customer = self.db.scalar(
            select(models.Customer).where(
                models.Customer.brand_id == brand_id,
                models.Customer.external_id == payload.customer_external_id,
            )
        )
        if customer:
            if payload.customer_name and not customer.display_name:
                customer.display_name = payload.customer_name
            if payload.customer_language and not customer.language:
                customer.language = payload.customer_language
            self.db.add(customer)
            self.db.flush()
            return customer

        customer = models.Customer(
            brand_id=brand_id,
            external_id=payload.customer_external_id,
            display_name=payload.customer_name,
            language=payload.customer_language,
            profile_json=payload.metadata.get("customer_profile", {}),
        )
        self.db.add(customer)
        self.db.flush()
        return customer

    def _get_or_create_conversation(self, brand_id: int, customer_id: int, payload: MessageProcessRequest) -> models.Conversation:
        conversation = self.db.scalar(
            select(models.Conversation).where(
                models.Conversation.brand_id == brand_id,
                models.Conversation.external_conversation_id == payload.conversation_external_id,
            )
        )
        if conversation:
            return conversation
        conversation = models.Conversation(
            brand_id=brand_id,
            customer_id=customer_id,
            channel=payload.channel,
            external_conversation_id=payload.conversation_external_id,
            metadata_json=payload.metadata,
            last_message_at=datetime.now(timezone.utc),
        )
        self.db.add(conversation)
        self.db.flush()
        return conversation

    def _build_llm_failure_fallback_reply(
        self,
        knowledge_hits: list,
    ) -> tuple[str | None, list[dict]]:
        if not knowledge_hits:
            return None, []

        top_hit = knowledge_hits[0]
        if getattr(top_hit, "score", 0.0) < 0.3:
            return None, []

        reply_text = self._extract_fallback_reply_text(getattr(top_hit, "content", ""))
        if not reply_text:
            return None, []

        return reply_text, [
            {
                "chunk_id": top_hit.chunk_id,
                "document_id": top_hit.document_id,
                "title": top_hit.title,
                "score": top_hit.score,
                "type": "knowledge_fallback",
            }
        ]

    def _extract_fallback_reply_text(self, content: str) -> str | None:
        normalized = " ".join((content or "").strip().split())
        if not normalized:
            return None

        sentences: list[str] = []
        buffer: list[str] = []
        for char in normalized:
            buffer.append(char)
            if char in ".!?।":
                sentence = "".join(buffer).strip()
                if sentence:
                    sentences.append(sentence)
                buffer = []
                if len(sentences) >= 2 or len(" ".join(sentences)) >= 220:
                    break

        if buffer and not sentences:
            sentences.append("".join(buffer).strip())

        candidate = " ".join(item for item in sentences if item).strip()
        if not candidate:
            candidate = normalized[:280].rsplit(" ", 1)[0].strip() or normalized[:280].strip()

        return candidate[:280].strip() or None

    def _bind_attachments(
        self,
        attachment_ids: list[int],
        brand_id: int,
        conversation_id: int,
        customer_id: int,
        message_id: int,
    ) -> list[models.Attachment]:
        if not attachment_ids:
            return []
        attachments = list(
            self.db.scalars(
                select(models.Attachment).where(
                    models.Attachment.id.in_(attachment_ids),
                    models.Attachment.brand_id == brand_id,
                )
            )
        )
        if len(attachments) != len(set(attachment_ids)):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="One or more attachments were not found.")

        for attachment in attachments:
            attachment.conversation_id = conversation_id
            attachment.customer_id = customer_id
            attachment.message_id = message_id
            self.db.add(attachment)
        self.db.flush()
        return attachments

    def _prepare_attachment_insights(
        self,
        attachments: list[models.Attachment],
        preferred_language: str | None,
    ) -> list[AttachmentInsight]:
        insights: list[AttachmentInsight] = []
        for attachment in attachments:
            if attachment.attachment_type == "audio":
                needs_refresh = not attachment.transcript
            elif attachment.attachment_type == "image":
                needs_refresh = not (
                    attachment.extracted_text
                    or (attachment.metadata_json or {}).get("summary")
                )
            else:
                needs_refresh = False
            if needs_refresh:
                file_bytes = read_file_bytes(attachment.storage_path)
                if attachment.attachment_type == "audio":
                    transcribed = self.speech_provider.transcribe_audio(
                        mime_type=attachment.mime_type,
                        data=file_bytes,
                        preferred_language=preferred_language,
                        alternative_languages=self.settings.speech_alt_language_list,
                    )
                    attachment.transcript = transcribed.transcript
                    attachment.translated_text = transcribed.translated_text
                    attachment.detected_language = transcribed.detected_language
                    attachment.analysis_confidence = transcribed.confidence
                    metadata = attachment.metadata_json or {}
                    metadata["summary"] = transcribed.summary
                    metadata["needs_clarification"] = transcribed.needs_clarification
                    metadata["clarification_reason"] = transcribed.clarification_reason
                    metadata["speech_provider"] = transcribed.provider_name
                    attachment.metadata_json = metadata
                    self.db.add(attachment)
                    insight = AttachmentInsight(
                        attachment_id=attachment.id,
                        attachment_type=attachment.attachment_type,
                        summary=transcribed.summary,
                        transcript=transcribed.transcript,
                        translated_text=transcribed.translated_text,
                        extracted_text=None,
                        detected_language=transcribed.detected_language,
                        analysis_confidence=transcribed.confidence,
                        needs_clarification=transcribed.needs_clarification,
                        clarification_reason=transcribed.clarification_reason,
                    )
                else:
                    analyzed = self.provider.analyze_attachment(
                        attachment_type=attachment.attachment_type,
                        mime_type=attachment.mime_type,
                        data=file_bytes,
                    )
                    attachment.transcript = analyzed.transcript
                    attachment.translated_text = analyzed.translated_text
                    attachment.extracted_text = analyzed.extracted_text
                    attachment.detected_language = analyzed.detected_language
                    attachment.analysis_confidence = analyzed.analysis_confidence
                    metadata = attachment.metadata_json or {}
                    metadata["summary"] = analyzed.summary
                    attachment.metadata_json = metadata
                    self.db.add(attachment)
                    insight = analyzed
            else:
                insight = AttachmentInsight(
                    attachment_id=attachment.id,
                    attachment_type=attachment.attachment_type,
                    summary=(attachment.metadata_json or {}).get("summary", f"{attachment.attachment_type} attachment received."),
                    transcript=attachment.transcript,
                    translated_text=attachment.translated_text,
                    extracted_text=attachment.extracted_text,
                    detected_language=attachment.detected_language,
                    analysis_confidence=attachment.analysis_confidence,
                    needs_clarification=bool((attachment.metadata_json or {}).get("needs_clarification", False)),
                    clarification_reason=(attachment.metadata_json or {}).get("clarification_reason"),
                )
            insight.attachment_id = attachment.id
            insights.append(insight)
        return insights

    def _recognize_product_images(
        self,
        brand_id: int,
        attachments: list[models.Attachment],
        customer_text: str = "",
    ) -> dict | None:
        """Check if customer images match any known products"""
        from app.services.product_recognition import ProductRecognizer

        recognizer = ProductRecognizer(self.db, brand_id)

        for attachment in attachments:
            if attachment.attachment_type == "image":
                try:
                    image_data = read_file_bytes(attachment.storage_path)
                    match = recognizer.recognize_product_from_image(
                        image_data=image_data,
                        mime_type=attachment.mime_type,
                        customer_text=customer_text,
                    )
                    if match.get("matched"):
                        return match
                except Exception:
                    # Skip if image processing fails
                    continue

        return None

    def _find_unclear_audio_insight(self, attachment_insights: list[AttachmentInsight]) -> AttachmentInsight | None:
        for item in attachment_insights:
            if item.attachment_type == "audio" and item.needs_clarification:
                return item
        return None
