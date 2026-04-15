from __future__ import annotations

import json
from typing import Any

from google import genai
from google.genai import types

from app.config import get_settings
from app.json_utils import to_json_compatible
from app.services.llm.base import (
    AttachmentInsight,
    BrandContext,
    ConversationTurn,
    CustomerSnapshot,
    KnowledgeSnippet,
    LLMProvider,
    ReplyDecision,
    SummaryResult,
)


class GeminiLLMProvider(LLMProvider):
    provider_name = "gemini"

    def __init__(self) -> None:
        self.settings = get_settings()
        self.client = genai.Client(api_key=self.settings.gemini_api_key)

    def generate_reply(
        self,
        brand: BrandContext,
        customer: CustomerSnapshot,
        history: list[ConversationTurn],
        incoming_text: str,
        knowledge: list[KnowledgeSnippet],
        attachment_insights: list[AttachmentInsight],
    ) -> ReplyDecision:
        prompt = self._build_reply_prompt(brand, customer, history, incoming_text, knowledge, attachment_insights)
        response = self.client.models.generate_content(model=self.settings.gemini_model, contents=prompt)
        payload = self._extract_json(getattr(response, "text", "") or "")
        return ReplyDecision(
            status=payload.get("status", "handoff"),
            reply_text=payload.get("reply_text", brand.fallback_handoff_message),
            confidence=float(payload.get("confidence", 0.4)),
            handoff_reason=payload.get("handoff_reason"),
            customer_updates=payload.get("customer_updates", {}),
            flags=payload.get("flags", []),
            used_knowledge_ids=payload.get("used_knowledge_ids", []),
            internal_notes=payload.get("internal_notes"),
            token_usage=self._serialize_usage_metadata(getattr(response, "usage_metadata", None)),
        )

    def summarize_conversation(self, brand: BrandContext, history: list[ConversationTurn]) -> SummaryResult:
        prompt = (
            "Summarize this customer support conversation in under 120 words and list stable customer facts. "
            "Return JSON only with keys summary and facts. facts must be an array of objects with key and value.\n\n"
            f"Brand: {brand.name}\n"
            f"History:\n{self._format_history(history)}"
        )
        response = self.client.models.generate_content(model=self.settings.gemini_summary_model, contents=prompt)
        payload = self._extract_json(getattr(response, "text", "") or "")
        return SummaryResult(summary=payload.get("summary", ""), facts=payload.get("facts", []))

    def analyze_attachment(self, attachment_type: str, mime_type: str, data: bytes) -> AttachmentInsight:
        prompt = (
            "Analyze this customer attachment for an ecommerce support agent. "
            "Return JSON only with keys summary, transcript, extracted_text. "
            "summary should explain what the attachment means for support. "
            "transcript is only for audio. extracted_text is for visible text in images or documents."
        )
        response = self.client.models.generate_content(
            model=self.settings.gemini_model,
            contents=[prompt, types.Part.from_bytes(data=data, mime_type=mime_type)],
        )
        payload = self._extract_json(getattr(response, "text", "") or "")
        return AttachmentInsight(
            attachment_id=0,
            attachment_type=attachment_type,
            summary=payload.get("summary", f"{attachment_type} attachment analyzed."),
            transcript=payload.get("transcript"),
            extracted_text=payload.get("extracted_text"),
        )

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        response = self.client.models.embed_content(model=self.settings.gemini_embedding_model, contents=texts)
        embeddings = getattr(response, "embeddings", None)
        if embeddings is None:
            embedding = getattr(response, "embedding", None)
            embeddings = [embedding] if embedding is not None else []
        vectors: list[list[float]] = []
        for item in embeddings:
            values = getattr(item, "values", item)
            vectors.append(list(values))
        return vectors

    def embed_image(self, image_data: bytes) -> list[float]:
        if "embedding-2" in self.settings.gemini_embedding_model:
            response = self.client.models.embed_content(
                model=self.settings.gemini_embedding_model,
                contents=[
                    types.Part.from_bytes(
                        data=image_data,
                        mime_type=self._guess_image_mime_type(image_data),
                    )
                ],
            )
            embeddings = getattr(response, "embeddings", None)
            if embeddings:
                values = getattr(embeddings[0], "values", embeddings[0])
                return list(values)

        # Fallback for text-only embedding models: describe the image, then embed the description.
        insight = self.analyze_attachment("image", "image/jpeg", image_data)
        text = " ".join(part for part in [insight.summary, insight.extracted_text] if part)
        vectors = self.embed_texts([text]) if text else []
        return vectors[0] if vectors else []

    def match_product_candidates(
        self,
        mime_type: str,
        data: bytes,
        candidates: list[dict[str, Any]],
    ) -> dict[str, Any] | None:
        if not candidates:
            return None

        prompt = (
            "You are matching a customer image to the most likely product from a small candidate list. "
            "Use the image itself as the main signal. "
            "Return JSON only with keys: matched, matched_candidate_id, confidence, explanation. "
            "Set matched to false if none of the candidates is a confident match.\n\n"
            f"Candidates:\n{json.dumps(candidates, ensure_ascii=True)}"
        )
        response = self.client.models.generate_content(
            model=self.settings.gemini_model,
            contents=[prompt, types.Part.from_bytes(data=data, mime_type=mime_type)],
        )
        payload = self._extract_json(getattr(response, "text", "") or "")
        if not payload:
            return None
        return payload

    def _build_reply_prompt(
        self,
        brand: BrandContext,
        customer: CustomerSnapshot,
        history: list[ConversationTurn],
        incoming_text: str,
        knowledge: list[KnowledgeSnippet],
        attachment_insights: list[AttachmentInsight],
    ) -> str:
        rules = "\n".join(
            f"- [{rule['category']}] {rule['title']}: {rule['content']}"
            for rule in brand.rules
        ) or "- No extra brand rules."
        style_examples = "\n".join(
            f"Example {idx + 1}\nCustomer: {item['trigger_text']}\nBest reply: {item['ideal_reply']}"
            for idx, item in enumerate(brand.style_examples[:5])
        ) or "No style examples."
        knowledge_text = "\n".join(
            f"[Chunk {item.chunk_id} | {item.title} | score={item.score:.3f}] {item.content}"
            for item in knowledge
        ) or "No matching knowledge was found."
        attachment_text = "\n".join(
            f"- {item.attachment_type}: {item.summary}. Transcript: {item.transcript or 'n/a'}. "
            f"Translated text: {item.translated_text or 'n/a'}. "
            f"Detected language: {item.detected_language or 'n/a'}. "
            f"Extracted text: {item.extracted_text or 'n/a'}"
            for item in attachment_insights
        ) or "No attachments."
        customer_text = json.dumps(
            {
                "display_name": customer.display_name,
                "language": customer.language,
                "city": customer.city,
                "summary": customer.short_summary,
                "profile": customer.profile,
                "facts": customer.facts,
            },
            ensure_ascii=True,
        )
        return (
            "You are generating a reply for a sales and customer support API. "
            "Be accurate, concise, and human. Never invent business facts. "
            "If the message is risky, unclear, legal, refund-related, abusive, or needs approval, choose handoff. "
            "If you need one short follow-up question, choose clarify. "
            "Return JSON only with keys: status, reply_text, confidence, handoff_reason, customer_updates, flags, used_knowledge_ids, internal_notes.\n\n"
            f"Brand name: {brand.name}\n"
            f"Preferred language: {brand.default_language}\n"
            f"Tone name: {brand.tone_name}\n"
            f"Tone instructions: {brand.tone_instructions or 'Keep it warm, clear, and sales-aware.'}\n"
            f"Public reply guidelines: {brand.public_reply_guidelines or 'No extra public rules.'}\n"
            f"Brand rules:\n{rules}\n\n"
            f"Style examples:\n{style_examples}\n\n"
            f"Customer snapshot: {customer_text}\n\n"
            f"Recent conversation:\n{self._format_history(history)}\n\n"
            f"Incoming customer message:\n{incoming_text}\n\n"
            f"Attachment insights:\n{attachment_text}\n\n"
            f"Knowledge candidates:\n{knowledge_text}\n\n"
            f"Language behavior: {self._language_instruction(brand.default_language, customer.language)}\n\n"
            "Reply_text should be customer-facing. customer_updates can include display_name, language, city, and facts. "
            "used_knowledge_ids should only contain chunk ids you actually used."
        )

    def _format_history(self, history: list[ConversationTurn]) -> str:
        if not history:
            return "No previous messages."
        return "\n".join(f"{turn.role}: {turn.text}" for turn in history[-12:])

    def _extract_json(self, text: str) -> dict[str, Any]:
        cleaned = text.strip()
        if "```" in cleaned:
            for part in cleaned.split("```"):
                candidate = part.replace("json", "", 1).strip()
                if candidate.startswith("{") and candidate.endswith("}"):
                    cleaned = candidate
                    break
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start != -1 and end != -1:
            cleaned = cleaned[start : end + 1]
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            return {}

    def _guess_image_mime_type(self, image_data: bytes) -> str:
        if image_data.startswith(b"\x89PNG\r\n\x1a\n"):
            return "image/png"
        if image_data.startswith(b"\xff\xd8\xff"):
            return "image/jpeg"
        if image_data.startswith(b"GIF87a") or image_data.startswith(b"GIF89a"):
            return "image/gif"
        if image_data.startswith(b"RIFF") and image_data[8:12] == b"WEBP":
            return "image/webp"
        return "image/jpeg"

    def _language_instruction(self, brand_language: str, customer_language: str | None) -> str:
        language = (customer_language or brand_language or "").lower()
        if self.settings.force_bangla_reply_by_default and language.startswith("bn"):
            return (
                "Reply in natural Bangla used in Bangladesh unless the customer clearly prefers English. "
                "If the customer mixes Bangla and English, mirror that style naturally."
            )
        return "Reply in the customer's apparent preferred language."

    def _serialize_usage_metadata(self, usage_metadata: Any) -> dict[str, Any]:
        if not usage_metadata:
            return {}
        serialized = to_json_compatible(usage_metadata)
        if isinstance(serialized, dict):
            return serialized
        return {"value": serialized}
