from __future__ import annotations

from typing import TYPE_CHECKING

from app.config import get_settings
from app.services.llm.base import LLMProvider
from app.services.llm.mock import MockLLMProvider
from app.services.llm.runtime import normalize_provider_name, resolve_llm_runtime_config

if TYPE_CHECKING:
    from app import models


def build_llm_provider(brand: models.Brand | None = None, *, modality: str = "text") -> LLMProvider:
    settings = get_settings()
    runtime = resolve_llm_runtime_config(brand, settings=settings, modality=modality)
    provider = normalize_provider_name(runtime.provider or settings.llm_provider)

    if provider == "gemini" and runtime.api_key:
        from app.services.llm.gemini import GeminiLLMProvider

        return GeminiLLMProvider(runtime)
    if provider == "groq" and runtime.api_key:
        from app.services.llm.groq import GroqLLMProvider

        return GroqLLMProvider(runtime)
    if provider in {"openai", "openrouter"} and runtime.api_key:
        from app.services.llm.openai_compatible import OpenAICompatibleLLMProvider

        return OpenAICompatibleLLMProvider(runtime)
    return MockLLMProvider()
