from __future__ import annotations

from unittest.mock import patch

from app.services.llm.gemini import GeminiLLMProvider


def test_gemini_analyze_attachment_falls_back_on_provider_failure(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    provider = GeminiLLMProvider()

    with patch.object(provider.client.models, "generate_content", side_effect=RuntimeError("429 RESOURCE_EXHAUSTED")):
        insight = provider.analyze_attachment("image", "image/png", b"test-image-bytes")

    assert insight.attachment_type == "image"
    assert "attachment received" in insight.summary.lower()
    assert insight.extracted_text is None


def test_gemini_match_product_candidates_returns_none_on_provider_failure(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    provider = GeminiLLMProvider()

    with patch.object(provider.client.models, "generate_content", side_effect=RuntimeError("429 RESOURCE_EXHAUSTED")):
        result = provider.match_product_candidates(
            "image/png",
            b"test-image-bytes",
            [{"candidate_id": 1, "product_name": "Demo", "category": "demo", "coarse_score": 0.9, "metadata": {}}],
        )

    assert result is None
