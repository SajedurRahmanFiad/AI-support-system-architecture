from __future__ import annotations

from app.config import get_settings
from app.services.llm.base import LLMProvider
from app.services.llm.gemini import GeminiLLMProvider
from app.services.llm.mock import MockLLMProvider


def build_llm_provider() -> LLMProvider:
    settings = get_settings()
    if settings.llm_provider == "gemini" and settings.gemini_api_key:
        return GeminiLLMProvider()
    return MockLLMProvider()
