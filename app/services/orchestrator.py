from __future__ import annotations

from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app import models
from app.api.schemas.messages import MessageProcessRequest, MessageProcessResponse
from app.config import get_settings
from app.services import knowledge, memory, moderation
from app.services.app_settings import get_global_reply_config, get_main_system_prompt
from app.services.billing import record_usage
from app.services.brand_service import get_brand_or_404
from app.services.llm.base import AttachmentInsight, ConversationTurn
from app.services.llm.factory import build_llm_provider
from app.services.speech import build_speech_provider, build_unclear_audio_reply
from app.services.storage import read_file_bytes


class MessageProcessor:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.settings = get_settings()
        self.provider = build_llm_provider()
        self.attachment_provider = build_llm_provider(modality="image")
        self.speech_provider = build_speech_provider()

    def process(self, payload: MessageProcessRequest) -> MessageProcessResponse:
        brand = get_brand_or_404(self.db, payload.brand_id)
        self.provider = build_llm_provider(brand, modality="text")
        self.attachment_provider = build_llm_provider(brand, modality="image")
        self.speech_provider = build_speech_provider(brand)
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
        self._record_attachment_usage(
            brand=brand,
            conversation_id=conversation.id,
            message_id=inbound_message.id,
            channel=payload.channel,
            attachment_insights=attachment_insights,
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
            self._remember_product_match(conversation, product_match)
            attachment_insights.append(
                AttachmentInsight(
                    attachment_id=product_match.get("product_image_id", 0),
                    attachment_type="product_match",
                    summary=self._build_product_fact_summary(product_match),
                    extracted_text=product_match.get("visual_summary"),
                )
            )

        history = memory.fetch_recent_history(self.db, conversation.id)[:-1]
        effective_customer_text, context_flags = self._resolve_effective_customer_text(
            payload=payload,
            conversation_id=conversation.id,
            current_message_id=inbound_message.id,
        )
        remembered_product = self._get_last_product_context(conversation)
        if remembered_product and not (product_match and product_match.get("matched")):
            attachment_insights.append(
                AttachmentInsight(
                    attachment_id=int(remembered_product.get("product_image_id") or 0),
                    attachment_type="product_context",
                    summary=self._build_product_fact_summary(remembered_product),
                    extracted_text=str((remembered_product.get("metadata") or {}).get("description") or "") or None,
                )
            )
        product_search_text = self._build_product_search_text(effective_customer_text, history, remembered_product)
        for candidate in self._search_products_by_text(brand.id, product_search_text):
            attachment_insights.append(
                AttachmentInsight(
                    attachment_id=int(candidate.get("primary_image_id") or 0),
                    attachment_type="product_catalog",
                    summary=self._build_product_fact_summary(candidate),
                    extracted_text=str((candidate.get("metadata") or {}).get("description") or "") or None,
                )
            )

        hydrated_brand = self.db.scalar(
            select(models.Brand)
            .options(joinedload(models.Brand.rules), joinedload(models.Brand.style_examples))
            .where(models.Brand.id == brand.id)
        ) or brand
        global_reply_config = get_global_reply_config(self.db)
        brand_context = memory.build_brand_context(
            hydrated_brand,
            system_prompt=get_main_system_prompt(self.db),
            global_reply_config=global_reply_config,
        )
        customer_snapshot = memory.build_customer_snapshot(customer)
        ad_id = self._extract_ad_id(payload.metadata) or self._extract_ad_id(conversation.metadata_json or {})

        moderation_text = " ".join(
            [effective_customer_text]
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

        if unclear_audio and not effective_customer_text.strip():
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
            record_usage(
                self.db,
                brand=brand,
                channel=payload.channel,
                usage_type="text",
                provider=self.speech_provider.provider_name,
                model=getattr(self.speech_provider, "runtime", None).model if getattr(self.speech_provider, "runtime", None) else getattr(unclear_audio, "model_name", None),
                token_usage=token_usage,
                message_units=1,
                conversation_id=conversation.id,
                message_id=outbound_message.id,
                metadata={
                    "status": decision_status,
                    "handoff_reason": handoff_reason,
                    "kind": "clarification_reply",
                },
            )
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
            moderation_text or effective_customer_text,
            ad_id=ad_id,
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
                f"{product_name} {alias_text} {effective_customer_text}".strip(),
                ad_id=ad_id,
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
            direct_product_reply = self._build_direct_product_reply(
                brand_default_language=brand.default_language,
                customer_language=customer.language,
                customer_text=effective_customer_text,
                product_match=product_match,
                remembered_product=remembered_product,
            )
            if direct_product_reply is not None:
                decision = None
                decision_status = "send"
                assign_human_owner = False
                confidence = direct_product_reply["confidence"]
                handoff_reason = None
                customer_updates = {}
                flags = list(dict.fromkeys(risk.flags + ["product-direct-reply"]))
                used_sources = [direct_product_reply["used_source"]]
                token_usage = {}
                reply_text = direct_product_reply["reply_text"]
            else:
                try:
                    decision = self.provider.generate_reply(
                        brand=brand_context,
                        customer=customer_snapshot,
                        history=history,
                        incoming_text=effective_customer_text,
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
        flags = list(dict.fromkeys(flags + context_flags))

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
        record_usage(
            self.db,
            brand=brand,
            channel=payload.channel,
            usage_type="text",
            provider=self.provider.provider_name,
            model=getattr(getattr(self.provider, "runtime", None), "model", None),
            token_usage=token_usage,
            message_units=1,
            conversation_id=conversation.id,
            message_id=outbound_message.id,
            metadata={
                "status": decision_status,
                "handoff_reason": handoff_reason,
            },
        )

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
            if payload.customer_name and payload.customer_name != customer.display_name:
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
            merged_metadata = self._merge_metadata_dicts(
                dict(conversation.metadata_json or {}),
                dict(payload.metadata or {}),
            )
            conversation.metadata_json = merged_metadata
            self.db.add(conversation)
            self.db.flush()
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

    def _resolve_effective_customer_text(
        self,
        *,
        payload: MessageProcessRequest,
        conversation_id: int,
        current_message_id: int,
    ) -> tuple[str, list[str]]:
        raw_text = (payload.text or "").strip()
        if not self._is_low_information_followup(raw_text):
            return raw_text, []

        reference_message = self._find_referenced_customer_message(
            conversation_id=conversation_id,
            current_message_id=current_message_id,
            metadata=payload.metadata,
        )
        if reference_message is None:
            return raw_text, []

        reference_text = self._build_message_reference_text(reference_message)
        if not reference_text:
            return raw_text, []

        if self._is_pure_marker_text(raw_text):
            return reference_text, ["reply-context:previous-message"]

        return (
            f"{reference_text}\n\nCustomer follow-up marker: {raw_text}",
            ["reply-context:previous-message"],
        )

    def _find_referenced_customer_message(
        self,
        *,
        conversation_id: int,
        current_message_id: int,
        metadata: dict | None,
    ) -> models.Message | None:
        explicit_reference_id = self._extract_reply_target_mid(metadata)
        if explicit_reference_id:
            explicit_match = self.db.scalar(
                select(models.Message)
                .options(joinedload(models.Message.attachments))
                .where(
                    models.Message.conversation_id == conversation_id,
                    models.Message.external_message_id == explicit_reference_id,
                    models.Message.role == "customer",
                )
            )
            if explicit_match is not None:
                return explicit_match

        recent_customer_messages = (
            self.db.execute(
                select(models.Message)
                .options(joinedload(models.Message.attachments))
                .where(
                    models.Message.conversation_id == conversation_id,
                    models.Message.role == "customer",
                    models.Message.id < current_message_id,
                )
                .order_by(models.Message.id.desc())
                .limit(8)
            )
            .unique()
            .scalars()
            .all()
        )
        for message in recent_customer_messages:
            if self._build_message_reference_text(message):
                return message
        return None

    def _build_message_reference_text(self, message: models.Message) -> str:
        parts: list[str] = []
        message_text = (message.text or "").strip()
        if message_text and not self._is_low_information_followup(message_text):
            parts.append(message_text)

        attachment_parts: list[str] = []
        for attachment in message.attachments:
            metadata = attachment.metadata_json if isinstance(attachment.metadata_json, dict) else {}
            summary = str(metadata.get("summary") or "").strip()
            if summary:
                attachment_parts.append(summary)
                continue
            if attachment.transcript:
                attachment_parts.append(attachment.transcript.strip())
                continue
            if attachment.extracted_text:
                attachment_parts.append(attachment.extracted_text.strip())
                continue
            attachment_parts.append(f"{attachment.attachment_type} attachment")

        if attachment_parts:
            parts.append("Referenced attachment context: " + " ".join(attachment_parts))

        return "\n".join(part for part in parts if part).strip()

    def _extract_reply_target_mid(self, metadata: dict | None) -> str | None:
        payload = metadata if isinstance(metadata, dict) else {}
        reply_to = payload.get("reply_to") if isinstance(payload.get("reply_to"), dict) else {}
        message_payload = payload.get("message") if isinstance(payload.get("message"), dict) else {}
        nested_reply_to = message_payload.get("reply_to") if isinstance(message_payload.get("reply_to"), dict) else {}
        candidates = [
            reply_to.get("mid"),
            reply_to.get("message_id"),
            nested_reply_to.get("mid"),
            nested_reply_to.get("message_id"),
        ]
        for candidate in candidates:
            cleaned = str(candidate or "").strip()
            if cleaned:
                return cleaned
        return None

    def _merge_metadata_dicts(self, existing: dict, incoming: dict) -> dict:
        merged = dict(existing)
        for key, value in incoming.items():
            if isinstance(value, dict):
                nested_existing = merged.get(key) if isinstance(merged.get(key), dict) else {}
                if value:
                    merged[key] = self._merge_metadata_dicts(dict(nested_existing), value)
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

    def _is_low_information_followup(self, text: str) -> bool:
        normalized = " ".join((text or "").split()).strip()
        if not normalized:
            return False
        if len(normalized) == 1:
            return True
        if all(not char.isalnum() for char in normalized):
            return True
        if len(normalized) <= 2 and normalized.isalpha():
            return True
        return False

    def _is_pure_marker_text(self, text: str) -> bool:
        normalized = " ".join((text or "").split()).strip()
        return bool(normalized) and all(not char.isalnum() for char in normalized)

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
                    metadata["provider_name"] = transcribed.provider_name
                    metadata["model_name"] = transcribed.model_name
                    metadata["token_usage"] = transcribed.token_usage or {}
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
                        provider_name=transcribed.provider_name,
                        model_name=transcribed.model_name,
                        token_usage=transcribed.token_usage or {},
                    )
                else:
                    analyzed = self.attachment_provider.analyze_attachment(
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
                    metadata["provider_name"] = analyzed.provider_name
                    metadata["model_name"] = analyzed.model_name
                    metadata["token_usage"] = analyzed.token_usage
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
                    provider_name=(attachment.metadata_json or {}).get("provider_name"),
                    model_name=(attachment.metadata_json or {}).get("model_name"),
                    token_usage=(attachment.metadata_json or {}).get("token_usage") or {},
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

    def _search_products_by_text(self, brand_id: int, customer_text: str) -> list[dict]:
        cleaned = " ".join((customer_text or "").split()).strip()
        if not cleaned:
            return []
        from app.services.product_recognition import ProductRecognizer

        recognizer = ProductRecognizer(self.db, brand_id)
        return recognizer.search_products_by_text(cleaned, limit=3)

    def _build_product_search_text(
        self,
        customer_text: str,
        history: list[ConversationTurn],
        remembered_product: dict | None = None,
    ) -> str:
        parts = [" ".join((customer_text or "").split()).strip()]
        for turn in history[-6:]:
            if turn.role == "customer":
                parts.append(" ".join((turn.text or "").split()).strip())
        if remembered_product:
            metadata = remembered_product.get("metadata") or {}
            parts.append(str(remembered_product.get("product_name") or "").strip())
            parts.extend(str(item).strip() for item in (metadata.get("aliases") or [])[:5] if str(item).strip())
            parts.extend(
                str(metadata.get(field) or "").strip()
                for field in ("model", "sku", "variant")
                if str(metadata.get(field) or "").strip()
            )
        return " ".join(part for part in parts if part).strip()

    def _remember_product_match(self, conversation: models.Conversation, product_match: dict) -> None:
        metadata = dict(conversation.metadata_json or {})
        metadata["last_product_match"] = {
            "product_name": product_match.get("product_name"),
            "category": product_match.get("category"),
            "metadata": product_match.get("metadata") or {},
            "product_image_id": product_match.get("product_image_id"),
            "confidence": product_match.get("confidence"),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        conversation.metadata_json = metadata
        self.db.add(conversation)

    def _get_last_product_context(self, conversation: models.Conversation) -> dict | None:
        payload = (conversation.metadata_json or {}).get("last_product_match")
        return payload if isinstance(payload, dict) else None

    def _build_direct_product_reply(
        self,
        *,
        brand_default_language: str | None,
        customer_language: str | None,
        customer_text: str,
        product_match: dict | None,
        remembered_product: dict | None,
    ) -> dict | None:
        candidate = product_match if product_match and product_match.get("matched") else remembered_product
        if not candidate:
            return None

        normalized_text = " ".join((customer_text or "").strip().lower().split())
        if not normalized_text and not (product_match and product_match.get("matched")):
            return None

        asks_stock = any(token in normalized_text for token in ("stock", "available", "availability", "in stock", "স্টক", "আছে", "পাব", "available?"))
        asks_price = any(token in normalized_text for token in ("price", "cost", "rate", "price?", "দাম", "কত", "মূল্য", "price er"))
        asks_product = any(token in normalized_text for token in ("this", "item", "product", "এটা", "এইটা", "পণ্য"))
        if normalized_text and not (asks_stock or asks_price or asks_product):
            return None

        metadata = candidate.get("metadata") or {}
        product_name = str(candidate.get("product_name") or "এই পণ্য").strip() or "এই পণ্য"
        sale_price = metadata.get("sale_price")
        stock_value = metadata.get("in_stock")
        in_stock = None
        if isinstance(stock_value, bool):
            in_stock = stock_value
        elif stock_value in {"1", "true", "yes", 1}:
            in_stock = True
        elif stock_value in {"0", "false", "no", 0}:
            in_stock = False

        language = (customer_language or brand_default_language or "").lower()
        if language.startswith("bn"):
            parts = [f"{product_name}"]
            if in_stock is True:
                parts.append("স্টকে আছে।")
            elif in_stock is False:
                parts.append("এখন স্টকে নেই।")
            if sale_price not in (None, "", []):
                parts.append(f"বিক্রয়মূল্য {sale_price} টাকা।")
            description = str(metadata.get("description") or "").strip()
            if not normalized_text and description:
                parts.append(description)
            reply_text = " ".join(parts).strip()
        else:
            parts = [product_name]
            if in_stock is True:
                parts.append("is in stock.")
            elif in_stock is False:
                parts.append("is currently out of stock.")
            if sale_price not in (None, "", []):
                parts.append(f"Sale price is {sale_price} BDT.")
            description = str(metadata.get("description") or "").strip()
            if not normalized_text and description:
                parts.append(description)
            reply_text = " ".join(parts).strip()

        if not reply_text:
            return None

        return {
            "reply_text": reply_text,
            "confidence": max(
                float((product_match or remembered_product or {}).get("confidence") or 0.0),
                self.settings.handoff_confidence_threshold,
            ),
            "used_source": {
                "type": "product_context",
                "product_name": product_name,
                "category": candidate.get("category"),
                "confidence": candidate.get("confidence"),
                "product_image_id": candidate.get("product_image_id"),
            },
        }

    def _build_product_fact_summary(self, product_match: dict) -> str:
        metadata = product_match.get("metadata") or {}
        stock_value = metadata.get("in_stock")
        if isinstance(stock_value, bool):
            stock_text = "In stock" if stock_value else "Out of stock"
        elif stock_value in {"1", "true", "yes", 1}:
            stock_text = "In stock"
        elif stock_value in {"0", "false", "no", 0}:
            stock_text = "Out of stock"
        else:
            stock_text = "Stock status not set"

        sale_price = metadata.get("sale_price")
        price_text = f"Sale price: {sale_price} BDT." if sale_price not in (None, "", []) else "Sale price not set."
        description = str(metadata.get("description") or "").strip()
        confidence = product_match.get("confidence")
        confidence_text = f" Match confidence: {float(confidence):.2f}." if confidence is not None else ""
        return (
            f"Product: {product_match.get('product_name', 'Unknown product')} "
            f"(category: {product_match.get('category', 'general')}). "
            f"{stock_text}. {price_text}"
            f"{' Description: ' + description + '.' if description else ''}"
            f"{confidence_text}"
        ).strip()

    def _extract_ad_id(self, metadata: dict | None) -> str | None:
        payload = metadata if isinstance(metadata, dict) else {}
        candidates = [
            payload.get("ad_id"),
            ((payload.get("message") or {}) if isinstance(payload.get("message"), dict) else {}).get("ad_id"),
            ((payload.get("referral") or {}) if isinstance(payload.get("referral"), dict) else {}).get("ad_id"),
            ((((payload.get("referral") or {}) if isinstance(payload.get("referral"), dict) else {}).get("ads_context_data") or {}) if isinstance(((payload.get("referral") or {}) if isinstance(payload.get("referral"), dict) else {}).get("ads_context_data"), dict) else {}).get("ad_id"),
        ]
        for candidate in candidates:
            cleaned = str(candidate or "").strip()
            if cleaned:
                return cleaned
        return None

    def _record_attachment_usage(
        self,
        *,
        brand: models.Brand,
        conversation_id: int,
        message_id: int,
        channel: str,
        attachment_insights: list[AttachmentInsight],
    ) -> None:
        for insight in attachment_insights:
            if insight.attachment_type not in {"audio", "image"}:
                continue
            token_usage = insight.token_usage or {}
            if not token_usage:
                continue
            record_usage(
                self.db,
                brand=brand,
                channel=channel,
                usage_type=insight.attachment_type,
                provider=insight.provider_name,
                model=insight.model_name,
                token_usage=token_usage,
                message_units=0,
                conversation_id=conversation_id,
                message_id=message_id,
                metadata={
                    "attachment_id": insight.attachment_id,
                    "needs_clarification": insight.needs_clarification,
                },
            )

    def _find_unclear_audio_insight(self, attachment_insights: list[AttachmentInsight]) -> AttachmentInsight | None:
        for item in attachment_insights:
            if item.attachment_type == "audio" and item.needs_clarification:
                return item
        return None
