from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app import models
from app.services.app_settings import get_global_reply_config, get_main_system_prompt


@dataclass
class CachedStaticPrompt:
    system_message: str
    rules_text: str
    style_examples_text: str
    tone_instructions: str
    public_reply_guidelines: str
    operational_contract: str
    brand_hash: str
    cached_at: datetime


class BrandPromptCache:
    _cache: dict[int, CachedStaticPrompt] = {}
    _settings_hash: str | None = None

    @classmethod
    def _compute_settings_hash(cls, db: Session) -> str:
        global_config = get_global_reply_config(db)
        main_prompt = get_main_system_prompt(db)
        content = json.dumps({"global_reply_config": global_config, "main_prompt": main_prompt}, sort_keys=True)
        return hashlib.sha256(content.encode()).hexdigest()[:16]

    @classmethod
    def _build_static_prompt(
        cls,
        brand: models.Brand,
        system_prompt: str,
        global_reply_config: dict[str, str],
    ) -> CachedStaticPrompt:
        reply_config = global_reply_config or {}
        global_tone = str(reply_config.get("tone_instructions") or "").strip()
        brand_tone = str(brand.tone_instructions or "").strip()
        global_guidelines = str(reply_config.get("public_reply_guidelines") or "").strip()
        brand_guidelines = str(brand.public_reply_guidelines or "").strip()

        merged_tone = cls._merge_sections(global_tone, brand_tone)
        merged_guidelines = cls._merge_sections(global_guidelines, brand_guidelines)

        rules = [
            f"- [{r.category}] {r.title}: {r.content}"
            for r in sorted(brand.rules, key=lambda x: x.priority)
        ]
        rules_text = "\n".join(rules) if rules else "- No extra brand rules."

        style_examples = [
            f"Example {i+1}\nCustomer: {e.trigger_text}\nBest reply: {e.ideal_reply}"
            for i, e in enumerate(sorted(brand.style_examples, key=lambda x: x.priority)[:3])
        ]
        style_examples_text = "\n".join(style_examples) if style_examples else "No style examples."

        brand_hash = hashlib.sha256(
            f"{brand.id}-{brand.updated_at.isoformat() if brand.updated_at else ''}".encode()
        ).hexdigest()[:12]

        operational_contract = (
            "Be accurate, concise, and human. Never invent business facts. "
            "If the message is risky, unclear, legal, refund-related, abusive, or needs approval, choose handoff. "
            "If you need one short follow-up question, choose clarify. "
            "Reason carefully about message timing and sequence. Use the timestamps in the recent conversation. "
            "Return JSON only with keys: status, reply_text, confidence, handoff_reason, customer_updates, flags, used_knowledge_ids, internal_notes."
        )

        system_message = f"{system_prompt or 'Use grounded, helpful sales and support behavior.'}\n\n{operational_contract}"

        return CachedStaticPrompt(
            system_message=system_message,
            rules_text=rules_text,
            style_examples_text=style_examples_text,
            tone_instructions=merged_tone,
            public_reply_guidelines=merged_guidelines,
            operational_contract=operational_contract,
            brand_hash=brand_hash,
            cached_at=datetime.now(timezone.utc),
        )

    @staticmethod
    def _merge_sections(*sections: str) -> str:
        merged: list[str] = []
        seen: set[str] = set()
        for section in sections:
            normalized = section.strip()
            if not normalized:
                continue
            key = " ".join(normalized.split()).casefold()
            if key in seen:
                continue
            seen.add(key)
            merged.append(normalized)
        return "\n\n".join(merged)

    @classmethod
    def get_static_prompt(cls, db: Session, brand: models.Brand) -> CachedStaticPrompt:
        current_settings_hash = cls._compute_settings_hash(db)

        cached = cls._cache.get(brand.id)
        if cached and cached.brand_hash == str(brand.id) + str(brand.updated_at):
            return cached

        system_prompt = get_main_system_prompt(db)
        global_config = get_global_reply_config(db)
        static = cls._build_static_prompt(brand, system_prompt, global_config)
        cls._cache[brand.id] = static
        return static

    @classmethod
    def invalidate(cls, brand_id: int) -> None:
        cls._cache.pop(brand_id, None)

    @classmethod
    def clear(cls) -> None:
        cls._cache.clear()


def get_knowledge_tools() -> list[dict[str, Any]]:
    return [
        {
            "type": "function",
            "function": {
                "name": "retrieve_knowledge",
                "description": "Search the brand's knowledge base for information relevant to answering the customer's question. Use this when the answer might be found in product info, policies, FAQs, or other documentation.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "The search query (1-3 keywords or short question)",
                        }
                    },
                    "required": ["query"],
                },
            },
        }
    ]


def parse_function_calls(response_content: str) -> list[dict[str, Any]] | None:
    try:
        if "```json" in response_content:
            for part in response_content.split("```"):
                if part.strip().startswith("json") or part.strip().startswith("{"):
                    if "retrieve_knowledge" in part:
                        start = part.find("{")
                        end = part.rfind("}") + 1
                        if start != -1 and end > start:
                            return json.loads(part[start:end])
        return None
    except Exception:
        return None