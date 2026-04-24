from __future__ import annotations

from unittest.mock import patch

from app.services.llm.base import AttachmentInsight, BrandContext, ConversationTurn, CustomerSnapshot
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


def test_gemini_generate_reply_normalizes_malformed_payload(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    provider = GeminiLLMProvider()

    class FakeResponse:
        text = (
            '{"status":"reply","reply_text":"Normalized reply","confidence":"0.85",'
            '"customer_updates":["bad"],"flags":{"reason":"llm-error"},'
            '"used_knowledge_ids":["9","oops"],"internal_notes":["note"]}'
        )
        usage_metadata = None

    brand = BrandContext(
        brand_id=1,
        name="SinoCross",
        default_language="bn-BD",
        tone_name="Helpful sales assistant",
        tone_instructions="Be helpful.",
        fallback_handoff_message="Please wait.",
        public_reply_guidelines=None,
    )
    customer = CustomerSnapshot(
        display_name="Customer",
        language="bn-BD",
        city=None,
        short_summary=None,
    )

    with patch.object(provider.client.models, "generate_content", return_value=FakeResponse()):
        decision = provider.generate_reply(
            brand=brand,
            customer=customer,
            history=[ConversationTurn(role="customer", text="Hello")],
            incoming_text="Need delivery info",
            knowledge=[],
            attachment_insights=[AttachmentInsight(attachment_id=1, attachment_type="image", summary="image summary")],
        )

    assert decision.reply_text == "Normalized reply"
    assert decision.confidence == 0.85
    assert decision.customer_updates == {}
    assert decision.flags == ["reason:llm-error"]
    assert decision.used_knowledge_ids == [9]
    assert decision.internal_notes == "['note']"


def test_gemini_generate_reply_retries_transient_errors(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    provider = GeminiLLMProvider()

    class FakeResponse:
        text = '{"status":"send","reply_text":"Recovered reply","confidence":0.8}'
        usage_metadata = None

    brand = BrandContext(
        brand_id=1,
        name="SinoCross",
        default_language="bn-BD",
        tone_name="Helpful sales assistant",
        tone_instructions="Be helpful.",
        fallback_handoff_message="Please wait.",
        public_reply_guidelines=None,
    )
    customer = CustomerSnapshot(
        display_name="Customer",
        language="bn-BD",
        city=None,
        short_summary=None,
    )

    with (
        patch.object(
            provider.client.models,
            "generate_content",
            side_effect=[RuntimeError("503 UNAVAILABLE"), FakeResponse()],
        ) as mocked_generate,
        patch("app.services.llm.gemini.time.sleep", return_value=None) as mocked_sleep,
    ):
        decision = provider.generate_reply(
            brand=brand,
            customer=customer,
            history=[ConversationTurn(role="customer", text="Hello")],
            incoming_text="Need delivery info",
            knowledge=[],
            attachment_insights=[],
        )

    assert decision.status == "send"
    assert decision.reply_text == "Recovered reply"
    assert mocked_generate.call_count == 2
    mocked_sleep.assert_called_once_with(1.0)
