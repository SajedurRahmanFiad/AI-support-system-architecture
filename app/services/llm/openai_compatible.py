from __future__ import annotations

import base64
import hashlib
import json
import time
from typing import Any

import httpx

from app.config import get_settings
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
from app.services.llm.runtime import LLMRuntimeConfig, resolve_llm_runtime_config


class OpenAICompatibleLLMProvider(LLMProvider):
    def __init__(self, runtime_config: LLMRuntimeConfig | None = None) -> None:
        self.settings = get_settings()
        self.runtime = runtime_config or resolve_llm_runtime_config()
        self.provider_name = self.runtime.provider
        self.base_url = (self.runtime.base_url or "https://api.openai.com/v1").rstrip("/")
        if not self.runtime.api_key:
            raise RuntimeError(f"{self.provider_name} provider requires an API key.")

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
        response_text, usage = self._chat_text_completion(model=self.runtime.model, prompt=prompt)
        payload = self._extract_json(response_text or "")
        reply_text = self._normalize_text(payload.get("reply_text")) or brand.fallback_handoff_message
        return ReplyDecision(
            status=self._normalize_text(payload.get("status")) or "handoff",
            reply_text=reply_text,
            confidence=self._normalize_float(payload.get("confidence"), default=0.4),
            handoff_reason=self._normalize_text(payload.get("handoff_reason")),
            customer_updates=self._normalize_dict(payload.get("customer_updates")),
            flags=self._normalize_string_list(payload.get("flags")),
            used_knowledge_ids=self._normalize_int_list(payload.get("used_knowledge_ids")),
            internal_notes=self._normalize_text(payload.get("internal_notes")),
            token_usage=usage,
        )

    def summarize_conversation(self, brand: BrandContext, history: list[ConversationTurn]) -> SummaryResult:
        prompt = (
            "Summarize this customer support conversation in under 120 words and list stable customer facts. "
            "Return JSON only with keys summary and facts. facts must be an array of objects with key and value.\n\n"
            f"Brand: {brand.name}\n"
            f"History:\n{self._format_history(history)}"
        )
        response_text, _usage = self._chat_text_completion(
            model=self.runtime.summary_model or self.runtime.model,
            prompt=prompt,
        )
        payload = self._extract_json(response_text or "")
        return SummaryResult(
            summary=self._normalize_text(payload.get("summary")) or "",
            facts=self._normalize_dict_list(payload.get("facts")),
        )

    def analyze_attachment(self, attachment_type: str, mime_type: str, data: bytes) -> AttachmentInsight:
        if attachment_type != "image":
            return AttachmentInsight(
                attachment_id=0,
                attachment_type=attachment_type,
                summary=self._fallback_attachment_summary(attachment_type, mime_type, data),
            )

        prompt = (
            "Analyze this customer image for an ecommerce support agent. "
            "Return JSON only with keys summary, transcript, extracted_text. "
            "summary should explain what the attachment means for support. "
            "transcript is only for audio. extracted_text is for visible text in images or documents."
        )
        try:
            response_text, _usage = self._chat_image_completion(
                model=self.runtime.model,
                prompt=prompt,
                mime_type=mime_type,
                data=data,
            )
            payload = self._extract_json(response_text or "")
            return AttachmentInsight(
                attachment_id=0,
                attachment_type=attachment_type,
                summary=payload.get("summary", f"{attachment_type} attachment analyzed."),
                transcript=payload.get("transcript"),
                extracted_text=payload.get("extracted_text"),
            )
        except Exception:
            return AttachmentInsight(
                attachment_id=0,
                attachment_type=attachment_type,
                summary=self._fallback_attachment_summary(attachment_type, mime_type, data),
                transcript=None,
                extracted_text=None,
            )

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        if not self.runtime.embedding_model:
            return [self._hashed_vector(text) for text in texts]

        payload = {
            "model": self.runtime.embedding_model,
            "input": texts,
        }
        response = self._post_json("/embeddings", payload)
        data = response.get("data")
        if not isinstance(data, list):
            return [self._hashed_vector(text) for text in texts]

        vectors: list[list[float]] = []
        for index, item in enumerate(data):
            embedding = item.get("embedding") if isinstance(item, dict) else None
            if isinstance(embedding, list) and embedding:
                vectors.append([float(value) for value in embedding])
            else:
                vectors.append(self._hashed_vector(texts[index]))
        return vectors

    def embed_image(self, image_data: bytes) -> list[float]:
        insight = self.analyze_attachment("image", "image/jpeg", image_data)
        text = " ".join(part for part in [insight.summary, insight.extracted_text] if part)
        vectors = self.embed_texts([text]) if text else []
        return vectors[0] if vectors else self._hashed_vector(image_data.hex())

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
        try:
            response_text, _usage = self._chat_image_completion(
                model=self.runtime.model,
                prompt=prompt,
                mime_type=mime_type,
                data=data,
            )
            payload = self._extract_json(response_text or "")
            return payload or None
        except Exception:
            return None

    def _chat_text_completion(self, *, model: str, prompt: str) -> tuple[str, dict[str, Any]]:
        payload = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
        }
        response = self._post_json("/chat/completions", payload)
        return self._extract_message_text(response), self._extract_usage(response)

    def _chat_image_completion(self, *, model: str, prompt: str, mime_type: str, data: bytes) -> tuple[str, dict[str, Any]]:
        payload = {
            "model": model,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": self._data_url(mime_type, data),
                                "detail": "auto",
                            },
                        },
                    ],
                }
            ],
        }
        response = self._post_json("/chat/completions", payload)
        return self._extract_message_text(response), self._extract_usage(response)

    def _post_json(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        last_error: Exception | None = None
        for attempt in range(3):
            try:
                merged_payload = dict(payload)
                if path == "/chat/completions":
                    if self.runtime.temperature is not None:
                        merged_payload["temperature"] = self.runtime.temperature
                    if self.runtime.top_p is not None:
                        merged_payload["top_p"] = self.runtime.top_p
                    if self.runtime.max_output_tokens is not None:
                        merged_payload["max_tokens"] = self.runtime.max_output_tokens
                    if self.runtime.top_k is not None and self.provider_name == "openrouter":
                        merged_payload["top_k"] = self.runtime.top_k

                response = httpx.post(
                    f"{self.base_url}{path}",
                    headers=self._headers(),
                    json=merged_payload,
                    timeout=30.0,
                )
                try:
                    data = response.json()
                except ValueError:
                    data = {"error": {"message": response.text}}

                if response.status_code >= 400:
                    detail = self._extract_error_detail(data) or response.text or f"HTTP {response.status_code}"
                    raise RuntimeError(detail)

                if not isinstance(data, dict):
                    raise RuntimeError("Provider returned an invalid JSON response.")
                return data
            except Exception as exc:  # noqa: BLE001
                last_error = exc
                if not self._is_retryable_error(exc) or attempt == 2:
                    raise
                time.sleep(float(attempt + 1))

        if last_error is not None:
            raise last_error
        raise RuntimeError("OpenAI-compatible completion failed without an exception.")

    def _headers(self) -> dict[str, str]:
        headers = {
            "Authorization": f"Bearer {self.runtime.api_key}",
            "Content-Type": "application/json",
        }
        headers.update(self.runtime.extra_headers)
        return headers

    def _extract_message_text(self, payload: dict[str, Any]) -> str:
        choices = payload.get("choices")
        if not isinstance(choices, list) or not choices:
            return ""
        message = choices[0].get("message") if isinstance(choices[0], dict) else None
        if not isinstance(message, dict):
            return ""
        content = message.get("content")
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts: list[str] = []
            for item in content:
                if not isinstance(item, dict):
                    continue
                text = item.get("text")
                if isinstance(text, str) and text.strip():
                    parts.append(text.strip())
            return "\n".join(parts)
        return ""

    def _extract_usage(self, payload: dict[str, Any]) -> dict[str, Any]:
        usage = payload.get("usage")
        return usage if isinstance(usage, dict) else {}

    @staticmethod
    def _extract_error_detail(payload: Any) -> str | None:
        if not isinstance(payload, dict):
            return None
        error = payload.get("error")
        if not isinstance(error, dict):
            return None
        message = str(error.get("message", "")).strip()
        code = str(error.get("code", "")).strip()
        parts = [item for item in (message, code) if item]
        return " | ".join(parts) if parts else None

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

    def _language_instruction(self, brand_language: str, customer_language: str | None) -> str:
        language = (customer_language or brand_language or "").lower()
        if self.settings.force_bangla_reply_by_default and language.startswith("bn"):
            return (
                "Reply in natural Bangla used in Bangladesh unless the customer clearly prefers English. "
                "If the customer mixes Bangla and English, mirror that style naturally."
            )
        return "Reply in the customer's apparent preferred language."

    def _is_retryable_error(self, exc: Exception) -> bool:
        message = str(exc).upper()
        retry_markers = (
            "429",
            "503",
            "RESOURCE_EXHAUSTED",
            "UNAVAILABLE",
            "RATE_LIMIT",
            "RETRYINFO",
            "TOO MANY REQUESTS",
            "TIMEOUT",
        )
        return any(marker in message for marker in retry_markers)

    def _normalize_text(self, value: Any) -> str | None:
        if value is None:
            return None
        normalized = str(value).strip()
        return normalized or None

    def _normalize_float(self, value: Any, *, default: float) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return default

    def _normalize_dict(self, value: Any) -> dict[str, Any]:
        if isinstance(value, dict):
            return value
        return {}

    def _normalize_dict_list(self, value: Any) -> list[dict[str, Any]]:
        if not isinstance(value, list):
            return []
        return [item for item in value if isinstance(item, dict)]

    def _normalize_string_list(self, value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, list):
            return [item.strip() for item in (str(item) for item in value) if item.strip()]
        if isinstance(value, dict):
            flattened = []
            for key, item in value.items():
                key_text = self._normalize_text(key)
                item_text = self._normalize_text(item)
                if key_text and item_text:
                    flattened.append(f"{key_text}:{item_text}")
                elif key_text:
                    flattened.append(key_text)
                elif item_text:
                    flattened.append(item_text)
            return flattened
        normalized = self._normalize_text(value)
        return [normalized] if normalized else []

    def _normalize_int_list(self, value: Any) -> list[int]:
        if isinstance(value, list):
            normalized: list[int] = []
            for item in value:
                try:
                    normalized.append(int(item))
                except (TypeError, ValueError):
                    continue
            return normalized
        return []

    def _hashed_vector(self, text: str) -> list[float]:
        digest = hashlib.sha256(text.encode("utf-8")).digest()
        return [float((byte - 128) / 128.0) for byte in digest[:24]]

    def _fallback_attachment_summary(self, attachment_type: str, mime_type: str, data: bytes) -> str:
        digest = hashlib.sha256(data).hexdigest()[:16]
        return f"{attachment_type} attachment received ({mime_type}, {len(data)} bytes, fingerprint {digest})."

    def _data_url(self, mime_type: str, data: bytes) -> str:
        encoded = base64.b64encode(data).decode("ascii")
        return f"data:{mime_type};base64,{encoded}"
