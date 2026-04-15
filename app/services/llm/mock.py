from __future__ import annotations

import hashlib
from collections import Counter

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


class MockLLMProvider(LLMProvider):
    provider_name = "mock"

    def generate_reply(
        self,
        brand: BrandContext,
        customer: CustomerSnapshot,
        history: list[ConversationTurn],
        incoming_text: str,
        knowledge: list[KnowledgeSnippet],
        attachment_insights: list[AttachmentInsight],
    ) -> ReplyDecision:
        lower = incoming_text.lower()
        if "refund" in lower or "manager" in lower:
            return ReplyDecision(
                status="handoff",
                reply_text=brand.fallback_handoff_message,
                confidence=0.92,
                handoff_reason="Sensitive topic needs human review.",
                flags=["mock-sensitive-topic"],
            )

        snippet = knowledge[0].content if knowledge else ""
        attachment_summary = attachment_insights[0].summary if attachment_insights else ""
        detail = snippet or attachment_summary or "I can help once you share a little more detail."
        reply = (
            f"Thanks for reaching out. Based on what I have right now, {detail[:350]}. "
            "If you want, I can help with the next step too."
        )
        return ReplyDecision(
            status="send",
            reply_text=reply,
            confidence=0.72 if knowledge else 0.58,
            customer_updates={
                "display_name": customer.display_name,
                "language": customer.language or brand.default_language,
                "facts": [],
            },
            used_knowledge_ids=[knowledge[0].chunk_id] if knowledge else [],
            flags=["mock-provider"],
        )

    def summarize_conversation(self, brand: BrandContext, history: list[ConversationTurn]) -> SummaryResult:
        recent = " ".join(turn.text for turn in history[-5:])
        return SummaryResult(summary=recent[:600] or "No conversation summary available yet.")

    def analyze_attachment(self, attachment_type: str, mime_type: str, data: bytes) -> AttachmentInsight:
        digest = hashlib.sha256(data).hexdigest()[:16]
        summary = f"{attachment_type} attachment received ({mime_type}, {len(data)} bytes, fingerprint {digest})."
        transcript = None
        translated_text = None
        detected_language = None
        analysis_confidence = None
        needs_clarification = False
        clarification_reason = None
        if attachment_type == "audio":
            if data.startswith(b"NOISY"):
                summary = "Audio attachment seems too noisy to understand clearly."
                analysis_confidence = 0.2
                needs_clarification = True
                clarification_reason = "Audio was too noisy in mock mode."
            else:
                transcript = f"Mock audio transcript {digest}"
                translated_text = transcript
                detected_language = "bn-BD"
                analysis_confidence = 0.92
        extracted_text = digest if attachment_type == "image" else None
        return AttachmentInsight(
            attachment_id=0,
            attachment_type=attachment_type,
            summary=summary,
            transcript=transcript,
            translated_text=translated_text,
            extracted_text=extracted_text,
            detected_language=detected_language,
            analysis_confidence=analysis_confidence,
            needs_clarification=needs_clarification,
            clarification_reason=clarification_reason,
        )

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        return [self._hashed_vector(text) for text in texts]

    def embed_image(self, image_data: bytes) -> list[float]:
        """Mock image embedding - returns a simple hash-based vector"""
        import hashlib
        digest = hashlib.sha256(image_data).digest()
        vector = [0.0] * 24
        for index in range(len(vector)):
            vector[index] = ((digest[index] / 255.0) - 0.5)
        return vector

    def _hashed_vector(self, text: str) -> list[float]:
        tokens = Counter(word.strip(".,!?").lower() for word in text.split() if word.strip())
        vector = [0.0] * 24
        for token, count in tokens.items():
            digest = hashlib.sha256(token.encode("utf-8")).digest()
            for index in range(len(vector)):
                vector[index] += ((digest[index] / 255.0) - 0.5) * count
        return vector
