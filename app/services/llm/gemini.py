from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import time
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
from app.services.llm.runtime import LLMRuntimeConfig, resolve_llm_runtime_config
from app.services.prompt_cache import get_knowledge_tools


class GeminiLLMProvider(LLMProvider):
    provider_name = "gemini"

    def __init__(self, runtime_config: LLMRuntimeConfig | None = None) -> None:
        self.settings = get_settings()
        self.runtime = runtime_config or resolve_llm_runtime_config(
            settings=self.settings,
            preferred_provider=self.provider_name,
        )
        if not self.runtime.api_key:
            raise RuntimeError("Gemini provider requires an API key.")
        self.client = genai.Client(api_key=self.runtime.api_key)

    def get_tools(self) -> list[dict[str, Any]]:
        return get_knowledge_tools()

    def generate_reply(
        self,
        brand: BrandContext,
        customer: CustomerSnapshot,
        history: list[ConversationTurn],
        incoming_text: str,
        knowledge: list[KnowledgeSnippet],
        attachment_insights: list[AttachmentInsight],
        tools: list[dict[str, Any]] | None = None,
        knowledge_search_fn: Any | None = None,
    ) -> ReplyDecision:
        messages = self._build_messages(
            brand=brand,
            customer=customer,
            history=history,
            incoming_text=incoming_text,
            knowledge=knowledge,
            attachment_insights=attachment_insights,
        )

        available_tools = tools or self.get_tools()

        if available_tools and knowledge_search_fn:
            response = self._chat_with_tools(model=self.runtime.model, messages=messages, tools=available_tools)
            response_text = response.get("content", "")
            tool_calls = response.get("tool_calls", [])
            usage = response.get("usage", {})

            if tool_calls:
                for tc in tool_calls:
                    if tc.get("function", {}).get("name") == "retrieve_knowledge":
                        try:
                            args = json.loads(tc["function"]["arguments"])
                            query = args.get("query", "")
                            if query and knowledge_search_fn:
                                fetched_knowledge = knowledge_search_fn(query)
                                messages.append({
                                    "role": "tool",
                                    "tool_call_id": tc["id"],
                                    "content": json.dumps(fetched_knowledge, ensure_ascii=True)
                                })
                        except Exception:
                            pass

                response2 = self._chat_with_tools(model=self.runtime.model, messages=messages, tools=None)
                response_text = response2.get("content", response_text)
                usage = {**usage, **response2.get("usage", {})}
        else:
            response = self._chat_with_tools(model=self.runtime.model, messages=messages, tools=None)
            response_text = response.get("content", "")
            usage = response.get("usage", {})

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

    def _build_messages(
        self,
        brand: BrandContext,
        customer: CustomerSnapshot,
        history: list[ConversationTurn],
        incoming_text: str,
        knowledge: list[KnowledgeSnippet],
        attachment_insights: list[AttachmentInsight],
    ) -> list[dict[str, Any]]:
        system_content = self._build_system_content(brand)
        user_content = self._build_user_content(
            brand=brand,
            customer=customer,
            history=history,
            incoming_text=incoming_text,
            knowledge=knowledge,
            attachment_insights=attachment_insights,
        )
        return [
            {"role": "system", "content": system_content},
            {"role": "user", "content": user_content},
        ]

    def _build_system_content(self, brand: BrandContext) -> str:
        rules = "\n".join(
            f"- [{r['category']}] {r['title']}: {r['content']}"
            for r in brand.rules
        ) or "- No extra brand rules."

        return (
            f"{brand.system_prompt or 'Use grounded, helpful sales and support behavior.'}\n\n"
            "Operational contract: "
            "Be accurate, concise, and human. Never invent business facts. "
            "If the message is risky, unclear, legal, refund-related, abusive, or needs approval, choose handoff. "
            "If you need one short follow-up question, choose clarify. "
            "Reason carefully about message timing and sequence. Use the timestamps in the recent conversation. "
            "Return JSON only with keys: status, reply_text, confidence, handoff_reason, customer_updates, flags, used_knowledge_ids, internal_notes.\n\n"
            f"Brand name: {brand.name}\n"
            f"Preferred language: {brand.default_language}\n"
            f"Tone name: {brand.tone_name}\n"
            f"Tone instructions: {brand.tone_instructions or 'Keep it warm, clear, and sales-aware.'}\n"
            f"Public reply guidelines: {brand.public_reply_guidelines or 'No extra public rules.'}\n"
            f"Brand rules:\n{rules}"
        )

    def _build_user_content(
        self,
        brand: BrandContext,
        customer: CustomerSnapshot,
        history: list[ConversationTurn],
        incoming_text: str,
        knowledge: list[KnowledgeSnippet],
        attachment_insights: list[AttachmentInsight],
    ) -> str:
        style_examples = "\n".join(
            f"Example {idx + 1}\nCustomer: {item['trigger_text']}\nBest reply: {item['ideal_reply']}"
            for idx, item in enumerate(brand.style_examples[:2])
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
            f"Current system time (UTC): {datetime.now(timezone.utc).isoformat()}\n\n"
            f"Customer snapshot: {customer_text}\n\n"
            f"Recent conversation:\n{self._format_history(history)}\n\n"
            f"Incoming customer message:\n{incoming_text}\n\n"
            f"Attachment insights:\n{attachment_text}\n\n"
            f"Style examples:\n{style_examples}\n\n"
            f"Knowledge candidates:\n{knowledge_text}\n\n"
            f"Language behavior: {self._language_instruction(brand.default_language, customer.language)}\n\n"
            "Reply_text should be customer-facing. customer_updates can include display_name, language, city, and facts. "
            "used_knowledge_ids should only contain chunk ids you actually used."
        )

    def _chat_with_tools(
        self,
        *,
        model: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None,
    ) -> dict[str, Any]:
        try:
            contents = []
            for msg in messages:
                role = msg.get("role", "user")
                if role == "system":
                    contents.append(types.Content(role="user", parts=[types.Part(text=msg.get("content", ""))]))
                    contents.append(types.Content(role="model", parts=[types.Part(text="Understood.")]))
                else:
                    contents.append(types.Content(role=role, parts=[types.Part(text=msg.get("content", ""))]))

            tool_config = None
            if tools:
                gemini_tools = [
                    types.Tool(
                        function_declarations=[
                            types.FunctionDeclaration(
                                name=tool["function"]["name"],
                                description=tool["function"].get("description", ""),
                                parameters=tool["function"].get("parameters", {}),
                            )
                        ]
                    )
                    for tool in tools
                ]
                tool_config = types.ToolConfig(function_calling_config=types.FunctionCallingConfig(mode="AUTO"))

            response = self.client.models.generate_content(
                model=model,
                contents=contents,
                tools=gemini_tools if tools else None,
                tool_config=tool_config,
            )

            content = getattr(response, "text", "") or ""
            usage = {}

            cand = response.candidates[0] if response.candidates else None
            if cand:
                func_calls = []
                for part in cand.content.parts:
                    if part.function_call:
                        fc = part.function_call
                        func_calls.append({
                            "id": f"call_{int(time.time())}",
                            "function": {
                                "name": fc.name,
                                "arguments": json.dumps({k: v for k, v in fc.args.items()})
                            }
                        })
                if func_calls:
                    return {"content": content, "tool_calls": func_calls, "usage": usage}

            return {"content": content, "usage": usage}
        except Exception as e:
            return {"content": f"{{\"error\": \"{str(e)}\"}}", "usage": {}}

    def summarize_conversation(self, brand: BrandContext, history: list[ConversationTurn]) -> SummaryResult:
        prompt = (
            "Summarize this customer support conversation in under 120 words and list stable customer facts. "
            "Return JSON only with keys summary and facts. facts must be an array of objects with key and value.\n\n"
            f"Brand: {brand.name}\n"
            f"History:\n{self._format_history(history)}"
        )
        response = self._generate_content(model=self.runtime.summary_model or self.runtime.model, contents=prompt)
        payload = self._extract_json(getattr(response, "text", "") or "")
        return SummaryResult(
            summary=self._normalize_text(payload.get("summary")) or "",
            facts=self._normalize_dict_list(payload.get("facts")),
        )

    def analyze_attachment(self, attachment_type: str, mime_type: str, data: bytes) -> AttachmentInsight:
        prompt = (
            "Analyze this customer attachment for an ecommerce support agent. "
            "Return JSON only with keys summary, transcript, extracted_text. "
            "summary should explain what the attachment means for support. "
            "transcript is only for audio. extracted_text is for visible text in images or documents."
        )
        try:
            response = self._generate_content(
                model=self.runtime.model,
                contents=[prompt, types.Part.from_bytes(data=data, mime_type=mime_type)],
            )
            payload = self._extract_json(getattr(response, "text", "") or "")
            return AttachmentInsight(
                attachment_id=0,
                attachment_type=attachment_type,
                summary=payload.get("summary", f"{attachment_type} attachment analyzed."),
                transcript=payload.get("transcript"),
                extracted_text=payload.get("extracted_text"),
                provider_name=self.provider_name,
                model_name=self.runtime.model,
                token_usage=self._serialize_usage_metadata(getattr(response, "usage_metadata", None)),
            )
        except Exception:
            return AttachmentInsight(
                attachment_id=0,
                attachment_type=attachment_type,
                summary=self._fallback_attachment_summary(attachment_type, mime_type, data),
                transcript=None,
                extracted_text=None,
                provider_name=self.provider_name,
                model_name=self.runtime.model,
            )

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        response = self.client.models.embed_content(
            model=self.runtime.embedding_model or self.settings.gemini_embedding_model,
            contents=texts,
        )
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
        embedding_model = self.runtime.embedding_model or self.settings.gemini_embedding_model
        if "embedding-2" in embedding_model:
            response = self.client.models.embed_content(
                model=embedding_model,
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

    def check_intent_completeness(self, text: str) -> str:
        if not text.strip():
            return "COMPLETE"
        prompt = (
            "Analyze the following user message to determine if their intent is complete, or if they are likely continuing to type more. "
            "Reply with exactly one word: 'COMPLETE' or 'INCOMPLETE'.\n\n"
            f"Message: {text}"
        )
        try:
            response = self._generate_content(model=self.runtime.model, contents=prompt)
            result = getattr(response, "text", "COMPLETE").strip().upper()
            if "INCOMPLETE" in result:
                return "INCOMPLETE"
            return "COMPLETE"
        except Exception:
            return "COMPLETE"

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
            response = self._generate_content(
                model=self.runtime.model,
                contents=[prompt, types.Part.from_bytes(data=data, mime_type=mime_type)],
            )
            payload = self._extract_json(getattr(response, "text", "") or "")
            if not payload:
                return None
            return payload
        except Exception:
            return None

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
            f"Main system prompt:\n{brand.system_prompt or 'Use grounded, helpful sales and support behavior.'}\n\n"
            "Operational contract: "
            "Be accurate, concise, and human. Never invent business facts. "
            "If the message is risky, unclear, legal, refund-related, abusive, or needs approval, choose handoff. "
            "If you need one short follow-up question, choose clarify. "
            "Reason carefully about message timing and sequence. Use the timestamps in the recent conversation to infer what happened first, what happened most recently, and whether the customer is referring to a very recent event. "
            "When knowledge candidates directly answer the customer, prefer using them instead of asking a redundant question. "
            "Return JSON only with keys: status, reply_text, confidence, handoff_reason, customer_updates, flags, used_knowledge_ids, internal_notes.\n\n"
            f"Current system time (UTC): {datetime.now(timezone.utc).isoformat()}\n"
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
            "Language behavior: {self._language_instruction(brand.default_language, customer.language)}\n\n"
            "Reply_text should be customer-facing. customer_updates can include display_name, language, city, and facts (an array of objects with 'key' and 'value'). "
            "used_knowledge_ids should only contain chunk ids you actually used."
        )

    def _format_history(self, history: list[ConversationTurn]) -> str:
        if not history:
            return "No previous messages."
        lines: list[str] = []
        for turn in history[-12:]:
            timestamp = turn.created_at.isoformat() if turn.created_at else "unknown-time"
            lines.append(f"[{timestamp}] {turn.role}: {turn.text}")
        return "\n".join(lines)

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

    def _generate_content(self, *, model: str, contents: Any) -> Any:
        last_error: Exception | None = None
        for attempt in range(3):
            try:
                config = self._generation_config()
                if config is not None:
                    return self.client.models.generate_content(model=model, contents=contents, config=config)
                return self.client.models.generate_content(model=model, contents=contents)
            except Exception as exc:  # noqa: BLE001
                last_error = exc
                if not self._is_retryable_error(exc) or attempt == 2:
                    raise
                time.sleep(float(attempt + 1))
        if last_error is not None:
            raise last_error
        raise RuntimeError("Gemini generate_content failed without an exception.")

    def _generation_config(self) -> types.GenerateContentConfig | None:
        if (
            self.runtime.temperature is None
            and self.runtime.top_p is None
            and self.runtime.top_k is None
            and self.runtime.max_output_tokens is None
        ):
            return None
        return types.GenerateContentConfig(
            temperature=self.runtime.temperature,
            top_p=self.runtime.top_p,
            top_k=self.runtime.top_k,
            max_output_tokens=self.runtime.max_output_tokens,
        )

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
        )
        return any(marker in message for marker in retry_markers)

    def _serialize_usage_metadata(self, usage_metadata: Any) -> dict[str, Any]:
        if not usage_metadata:
            return {}
        serialized = to_json_compatible(usage_metadata)
        if isinstance(serialized, dict):
            return serialized
        return {"value": serialized}

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

    def _fallback_attachment_summary(self, attachment_type: str, mime_type: str, data: bytes) -> str:
        digest = hashlib.sha256(data).hexdigest()[:16]
        return f"{attachment_type} attachment received ({mime_type}, {len(data)} bytes, fingerprint {digest})."
