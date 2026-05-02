from __future__ import annotations

from app.config import get_settings
from app.services.speech import GeminiSpeechProvider


def test_gemini_speech_provider_normalizes_video_mp4_to_audio_mp4(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    get_settings.cache_clear()

    provider = GeminiSpeechProvider()

    assert provider._normalize_audio_mime_type("video/mp4") == "audio/mp4"
    assert provider._normalize_audio_mime_type("audio/mp4") == "audio/mp4"
