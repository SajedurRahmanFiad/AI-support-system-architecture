from __future__ import annotations

import json
import tempfile
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from google import genai
from google.genai import types

from app.config import get_settings
from app.services.llm.runtime import LLMRuntimeConfig, extract_brand_processing_settings, normalize_provider_name, resolve_llm_runtime_config


@dataclass
class SpeechTranscriptionResult:
    transcript: str | None
    translated_text: str | None
    detected_language: str | None
    confidence: float | None
    summary: str
    needs_clarification: bool
    clarification_reason: str | None
    provider_name: str
    model_name: str | None = None
    token_usage: dict[str, Any] | None = None


class SpeechProvider(ABC):
    provider_name: str = "base"

    @abstractmethod
    def transcribe_audio(
        self,
        mime_type: str,
        data: bytes,
        preferred_language: str | None,
        alternative_languages: list[str],
    ) -> SpeechTranscriptionResult:
        raise NotImplementedError


class MockSpeechProvider(SpeechProvider):
    provider_name = "mock"

    def transcribe_audio(
        self,
        mime_type: str,
        data: bytes,
        preferred_language: str | None,
        alternative_languages: list[str],
    ) -> SpeechTranscriptionResult:
        if data.startswith(b"NOISY"):
            return SpeechTranscriptionResult(
                transcript=None,
                translated_text=None,
                detected_language=preferred_language or "bn-BD",
                confidence=0.2,
                summary="Audio was too noisy to transcribe clearly.",
                needs_clarification=True,
                clarification_reason="Audio was too noisy in mock mode.",
                provider_name=self.provider_name,
                model_name="mock",
                token_usage={},
            )
        return SpeechTranscriptionResult(
            transcript="Mock audio transcript",
            translated_text="Mock audio transcript",
            detected_language=preferred_language or "bn-BD",
            confidence=0.95,
            summary="Clear mock voice note transcript ready.",
            needs_clarification=False,
            clarification_reason=None,
            provider_name=self.provider_name,
            model_name="mock",
            token_usage={},
        )


class GeminiSpeechProvider(SpeechProvider):
    provider_name = "gemini"

    def __init__(self, runtime_config: LLMRuntimeConfig | None = None) -> None:
        self.settings = get_settings()
        self.runtime = runtime_config or resolve_llm_runtime_config(settings=self.settings, modality="audio", preferred_provider="gemini")
        self.client = genai.Client(api_key=self.runtime.api_key or self.settings.gemini_api_key)

    def transcribe_audio(
        self,
        mime_type: str,
        data: bytes,
        preferred_language: str | None,
        alternative_languages: list[str],
    ) -> SpeechTranscriptionResult:
        prompt = self._build_prompt(preferred_language, alternative_languages)
        uploaded_file_name: str | None = None
        temp_path: Path | None = None
        try:
            if len(data) > self.settings.gemini_inline_audio_max_bytes:
                suffix = self._suffix_for_mime_type(mime_type)
                with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as temp_file:
                    temp_file.write(data)
                    temp_path = Path(temp_file.name)
                uploaded = self.client.files.upload(
                    file=str(temp_path),
                    config={"mimeType": mime_type},
                )
                uploaded_file_name = uploaded.name
                response = self.client.models.generate_content(
                    model=self.runtime.model or self.settings.gemini_model,
                    contents=[prompt, uploaded],
                )
            else:
                response = self.client.models.generate_content(
                    model=self.runtime.model or self.settings.gemini_model,
                    contents=[prompt, types.Part.from_bytes(data=data, mime_type=mime_type)],
                )
        finally:
            if temp_path and temp_path.exists():
                temp_path.unlink(missing_ok=True)

        try:
            payload = self._extract_json(getattr(response, "text", "") or "")
        finally:
            if uploaded_file_name:
                try:
                    self.client.files.delete(name=uploaded_file_name)
                except Exception:  # noqa: BLE001
                    pass

        transcript = (payload.get("transcript") or "").strip() or None
        translated_text = (payload.get("translated_text") or "").strip() or None
        detected_language = (payload.get("detected_language") or preferred_language or "").strip() or None
        confidence = self._safe_float(payload.get("confidence"))
        summary = (payload.get("summary") or transcript or "Audio was analyzed.").strip()
        needs_clarification = bool(payload.get("needs_clarification", False))
        clarification_reason = (payload.get("clarification_reason") or "").strip() or None

        if not transcript:
            needs_clarification = True
            clarification_reason = clarification_reason or "No reliable transcript was produced."
        if confidence is not None and confidence < self.settings.speech_low_confidence_threshold:
            needs_clarification = True
            clarification_reason = clarification_reason or "The transcript confidence was too low."

        return SpeechTranscriptionResult(
            transcript=transcript,
            translated_text=translated_text,
            detected_language=detected_language,
            confidence=confidence,
            summary=summary,
            needs_clarification=needs_clarification,
            clarification_reason=clarification_reason,
            provider_name=self.provider_name,
            model_name=self.runtime.model or self.settings.gemini_model,
            token_usage=self._serialize_usage_metadata(getattr(response, "usage_metadata", None)),
        )

    def _build_prompt(self, preferred_language: str | None, alternative_languages: list[str]) -> str:
        language_text = ", ".join(dict.fromkeys([preferred_language or "bn-BD", *alternative_languages]))
        return (
            "You transcribe customer voice notes for a Bangladesh-focused ecommerce support system. "
            "Return JSON only with keys: transcript, translated_text, detected_language, confidence, summary, "
            "needs_clarification, clarification_reason. "
            "Rules: Keep transcript in the original spoken language. "
            "If the speaker uses Bangla or mixed Bangla-English, preserve that naturally. "
            "If the transcript is not English, translated_text should be a short English translation. "
            "confidence must be a number from 0 to 1. "
            "needs_clarification must be true when the audio is too noisy, too short, too unclear, or not reliable enough. "
            f"Expected languages: {language_text}."
        )

    def _extract_json(self, text: str) -> dict:
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

    def _safe_float(self, value: object) -> float | None:
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    def _serialize_usage_metadata(self, usage_metadata: Any) -> dict[str, Any]:
        if not usage_metadata:
            return {}
        if hasattr(usage_metadata, "model_dump"):
            try:
                dumped = usage_metadata.model_dump()
                if isinstance(dumped, dict):
                    return dumped
            except Exception:  # noqa: BLE001
                pass
        if isinstance(usage_metadata, dict):
            return usage_metadata
        return {"value": str(usage_metadata)}

    def _suffix_for_mime_type(self, mime_type: str) -> str:
        mapping = {
            "audio/wav": ".wav",
            "audio/x-wav": ".wav",
            "audio/mp3": ".mp3",
            "audio/mpeg": ".mp3",
            "audio/aac": ".aac",
            "audio/ogg": ".ogg",
            "audio/flac": ".flac",
            "audio/aiff": ".aiff",
            "audio/mp4": ".m4a",
        }
        return mapping.get(mime_type, ".bin")


class GoogleCloudSpeechProvider(SpeechProvider):
    provider_name = "google_cloud"

    def __init__(self) -> None:
        self.settings = get_settings()
        if not self.settings.google_cloud_project_id:
            raise RuntimeError("GOOGLE_CLOUD_PROJECT_ID is required for Google Cloud Speech.")

    def transcribe_audio(
        self,
        mime_type: str,
        data: bytes,
        preferred_language: str | None,
        alternative_languages: list[str],
    ) -> SpeechTranscriptionResult:
        try:
            from google.cloud import speech_v2
            from google.cloud.speech_v2.types import cloud_speech
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError("google-cloud-speech is not available.") from exc

        language_codes = list(dict.fromkeys([preferred_language or self.settings.speech_primary_language, *alternative_languages]))
        client = speech_v2.SpeechClient()
        config = cloud_speech.RecognitionConfig(
            auto_decoding_config=cloud_speech.AutoDetectDecodingConfig(),
            language_codes=language_codes,
            model="long",
            features=cloud_speech.RecognitionFeatures(enable_automatic_punctuation=True),
        )
        request = cloud_speech.RecognizeRequest(
            recognizer=f"projects/{self.settings.google_cloud_project_id}/locations/global/recognizers/_",
            config=config,
            content=data,
        )
        response = client.recognize(request=request)

        transcripts: list[str] = []
        confidence_values: list[float] = []
        detected_language = preferred_language or self.settings.speech_primary_language
        for result in response.results:
            if getattr(result, "language_code", None):
                detected_language = result.language_code
            alternatives = list(getattr(result, "alternatives", []))
            if not alternatives:
                continue
            best = alternatives[0]
            transcript = getattr(best, "transcript", "").strip()
            if transcript:
                transcripts.append(transcript)
            confidence = getattr(best, "confidence", None)
            if confidence is not None and confidence > 0:
                confidence_values.append(float(confidence))

        transcript_text = " ".join(transcripts).strip() or None
        average_confidence = sum(confidence_values) / len(confidence_values) if confidence_values else None
        needs_clarification = not transcript_text
        clarification_reason = None
        if average_confidence is not None and average_confidence < self.settings.speech_low_confidence_threshold:
            needs_clarification = True
            clarification_reason = "Speech-to-text confidence was low."
        if not transcript_text:
            clarification_reason = clarification_reason or "No reliable transcript was produced."

        summary = transcript_text[:240] if transcript_text else "Audio could not be transcribed clearly."
        return SpeechTranscriptionResult(
            transcript=transcript_text,
            translated_text=None,
            detected_language=detected_language,
            confidence=average_confidence,
            summary=summary,
            needs_clarification=needs_clarification,
            clarification_reason=clarification_reason,
            provider_name=self.provider_name,
            model_name="google_cloud:long",
            token_usage={},
        )


def build_speech_provider(brand: object | None = None) -> SpeechProvider:
    settings = get_settings()
    brand_model = brand if hasattr(brand, "settings_json") else None
    brand_audio_settings = extract_brand_processing_settings(brand_model, "audio")
    provider_name = normalize_provider_name(brand_audio_settings.get("provider") or settings.speech_provider)
    runtime = resolve_llm_runtime_config(
        brand_model,
        settings=settings,
        modality="audio",
        preferred_provider="gemini" if provider_name == "gemini" else settings.llm_provider,
    )

    if provider_name == "google_cloud":
        try:
            return GoogleCloudSpeechProvider()
        except Exception:  # noqa: BLE001
            if runtime.api_key or settings.gemini_api_key:
                return GeminiSpeechProvider(runtime if runtime.provider == "gemini" else None)
            return MockSpeechProvider()
    if provider_name == "gemini" and (runtime.api_key or settings.gemini_api_key):
        return GeminiSpeechProvider(runtime)
    return MockSpeechProvider()


def build_unclear_audio_reply(language_code: str | None) -> str:
    settings = get_settings()
    language = (language_code or "").lower()
    if language.startswith("bn"):
        return settings.unclear_audio_reply_bn
    return settings.unclear_audio_reply_en
