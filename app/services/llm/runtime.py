from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from app.config import Settings, get_settings

if TYPE_CHECKING:
    from app import models


PROVIDER_LABELS = {
    "gemini": "Google",
    "openai": "OpenAI",
    "groq": "Groq",
    "openrouter": "OpenRouter",
    "mock": "Mock",
}

SUPPORTED_MODALITIES = {"text", "image", "audio"}


@dataclass
class LLMRuntimeConfig:
    provider: str
    model: str
    api_key: str | None = None
    summary_model: str | None = None
    embedding_model: str | None = None
    temperature: float | None = None
    top_p: float | None = None
    top_k: int | None = None
    max_output_tokens: int | None = None
    site_url: str | None = None
    app_name: str | None = None
    base_url: str | None = None
    extra_headers: dict[str, str] = field(default_factory=dict)


def normalize_provider_name(value: str | None) -> str:
    normalized = str(value or "").strip().lower()
    aliases = {
        "google": "gemini",
        "gemini": "gemini",
        "openai": "openai",
        "groq": "groq",
        "openrouter": "openrouter",
        "mock": "mock",
    }
    return aliases.get(normalized, "mock")


def provider_label(provider: str) -> str:
    return PROVIDER_LABELS.get(normalize_provider_name(provider), provider.title())


def default_model_for_provider(provider: str, settings: Settings | None = None) -> str:
    settings = settings or get_settings()
    normalized = normalize_provider_name(provider)
    if normalized == "gemini":
        return settings.gemini_model
    if normalized == "groq":
        return settings.groq_model
    if normalized == "openai":
        return settings.openai_model
    if normalized == "openrouter":
        return settings.openrouter_model
    return "mock"


def default_summary_model_for_provider(provider: str, settings: Settings | None = None) -> str | None:
    settings = settings or get_settings()
    normalized = normalize_provider_name(provider)
    if normalized == "gemini":
        return settings.gemini_summary_model
    if normalized == "openai":
        return settings.openai_summary_model
    if normalized == "openrouter":
        return settings.openrouter_summary_model
    return None


def default_embedding_model_for_provider(provider: str, settings: Settings | None = None) -> str | None:
    settings = settings or get_settings()
    normalized = normalize_provider_name(provider)
    if normalized == "gemini":
        return settings.gemini_embedding_model
    if normalized == "openai":
        return settings.openai_embedding_model
    if normalized == "openrouter":
        return settings.openrouter_embedding_model
    return None


def default_api_key_for_provider(provider: str, settings: Settings | None = None) -> str | None:
    settings = settings or get_settings()
    normalized = normalize_provider_name(provider)
    if normalized == "gemini":
        return _strip_or_none(settings.gemini_api_key)
    if normalized == "groq":
        return _strip_or_none(settings.groq_api_key)
    if normalized == "openai":
        return _strip_or_none(settings.openai_api_key)
    if normalized == "openrouter":
        return _strip_or_none(settings.openrouter_api_key)
    return None


def default_site_url_for_provider(provider: str, settings: Settings | None = None) -> str | None:
    settings = settings or get_settings()
    if normalize_provider_name(provider) == "openrouter":
        return _strip_or_none(settings.openrouter_site_url)
    return None


def default_app_name_for_provider(provider: str, settings: Settings | None = None) -> str | None:
    settings = settings or get_settings()
    if normalize_provider_name(provider) == "openrouter":
        return _strip_or_none(settings.openrouter_app_name)
    return None


def extract_brand_llm_settings(brand: models.Brand | None) -> dict[str, Any]:
    if brand is None or not isinstance(brand.settings_json, dict):
        return {}
    llm = brand.settings_json.get("llm")
    return llm if isinstance(llm, dict) else {}


def extract_brand_processing_settings(brand: models.Brand | None, modality: str = "text") -> dict[str, Any]:
    normalized_modality = (modality or "text").strip().lower()
    if normalized_modality not in SUPPORTED_MODALITIES:
        normalized_modality = "text"
    if brand is None or not isinstance(brand.settings_json, dict):
        return {}
    processing = brand.settings_json.get("processing")
    if isinstance(processing, dict):
        modality_settings = processing.get(normalized_modality)
        if isinstance(modality_settings, dict):
            return modality_settings
    if normalized_modality == "text":
        return extract_brand_llm_settings(brand)
    return {}


def extract_brand_billing_settings(brand: models.Brand | None) -> dict[str, Any]:
    if brand is None or not isinstance(brand.settings_json, dict):
        return {}
    billing = brand.settings_json.get("billing")
    return billing if isinstance(billing, dict) else {}


def resolve_llm_runtime_config(
    brand: models.Brand | None = None,
    settings: Settings | None = None,
    *,
    preferred_provider: str | None = None,
    modality: str = "text",
) -> LLMRuntimeConfig:
    settings = settings or get_settings()
    normalized_modality = (modality or "text").strip().lower()
    brand_settings = extract_brand_processing_settings(brand, normalized_modality)

    fallback_provider = preferred_provider or settings.llm_provider
    if normalized_modality in {"image", "audio"} and not brand_settings:
        if settings.gemini_api_key:
            fallback_provider = "gemini"
        else:
            fallback_provider = preferred_provider or settings.llm_provider

    provider = normalize_provider_name(brand_settings.get("provider") or fallback_provider)
    model = _strip_or_none(brand_settings.get("model")) or default_model_for_provider(provider, settings)
    api_key = _strip_or_none(brand_settings.get("api_key")) or default_api_key_for_provider(provider, settings)
    summary_model = _strip_or_none(brand_settings.get("summary_model")) or default_summary_model_for_provider(provider, settings) or model
    embedding_model = _strip_or_none(brand_settings.get("embedding_model")) or default_embedding_model_for_provider(provider, settings)
    temperature = _safe_float(brand_settings.get("temperature"), default=0.7)
    top_p = _safe_float(brand_settings.get("top_p"))
    top_k = _safe_int(brand_settings.get("top_k"))
    max_output_tokens = _safe_int(brand_settings.get("max_output_tokens"))
    site_url = _strip_or_none(brand_settings.get("site_url")) or default_site_url_for_provider(provider, settings)
    app_name = _strip_or_none(brand_settings.get("app_name")) or default_app_name_for_provider(provider, settings)
    base_url = None
    extra_headers: dict[str, str] = {}
    if provider == "openrouter":
        base_url = "https://openrouter.ai/api/v1"
        if site_url:
            extra_headers["HTTP-Referer"] = site_url
        if app_name:
            extra_headers["X-Title"] = app_name

    return LLMRuntimeConfig(
        provider=provider,
        model=model,
        api_key=api_key,
        summary_model=summary_model,
        embedding_model=embedding_model,
        temperature=temperature,
        top_p=top_p,
        top_k=top_k,
        max_output_tokens=max_output_tokens,
        site_url=site_url,
        app_name=app_name,
        base_url=base_url,
        extra_headers=extra_headers,
    )


def merge_brand_llm_settings(
    current_settings: dict[str, Any] | None,
    llm_settings: dict[str, Any] | None,
) -> dict[str, Any]:
    settings_json = dict(current_settings or {})
    if llm_settings is None:
        return settings_json
    normalized = {
        "provider": normalize_provider_name(llm_settings.get("provider")),
        "model": _strip_or_none(llm_settings.get("model")),
        "api_key": _strip_or_none(llm_settings.get("api_key")),
        "summary_model": _strip_or_none(llm_settings.get("summary_model")),
        "embedding_model": _strip_or_none(llm_settings.get("embedding_model")),
        "temperature": _safe_float(llm_settings.get("temperature")),
        "top_p": _safe_float(llm_settings.get("top_p")),
        "top_k": _safe_int(llm_settings.get("top_k")),
        "max_output_tokens": _safe_int(llm_settings.get("max_output_tokens")),
        "site_url": _strip_or_none(llm_settings.get("site_url")),
        "app_name": _strip_or_none(llm_settings.get("app_name")),
    }
    settings_json["llm"] = {key: value for key, value in normalized.items() if value not in (None, "", [])}
    return settings_json


def merge_brand_processing_settings(
    current_settings: dict[str, Any] | None,
    modality: str,
    llm_settings: dict[str, Any] | None,
) -> dict[str, Any]:
    settings_json = dict(current_settings or {})
    normalized_modality = (modality or "text").strip().lower()
    if normalized_modality not in SUPPORTED_MODALITIES or llm_settings is None:
        return settings_json

    processing = dict(settings_json.get("processing") or {})
    normalized = {
        "provider": normalize_provider_name(llm_settings.get("provider")),
        "model": _strip_or_none(llm_settings.get("model")),
        "api_key": _strip_or_none(llm_settings.get("api_key")),
        "summary_model": _strip_or_none(llm_settings.get("summary_model")),
        "embedding_model": _strip_or_none(llm_settings.get("embedding_model")),
        "temperature": _safe_float(llm_settings.get("temperature")),
        "top_p": _safe_float(llm_settings.get("top_p")),
        "top_k": _safe_int(llm_settings.get("top_k")),
        "max_output_tokens": _safe_int(llm_settings.get("max_output_tokens")),
        "site_url": _strip_or_none(llm_settings.get("site_url")),
        "app_name": _strip_or_none(llm_settings.get("app_name")),
    }
    processing[normalized_modality] = {key: value for key, value in normalized.items() if value not in (None, "", [])}
    settings_json["processing"] = processing
    if normalized_modality == "text":
        settings_json["llm"] = dict(processing[normalized_modality])
    return settings_json


def merge_brand_billing_settings(
    current_settings: dict[str, Any] | None,
    billing_settings: dict[str, Any] | None,
) -> dict[str, Any]:
    settings_json = dict(current_settings or {})
    if billing_settings is None:
        return settings_json

    billing = dict(settings_json.get("billing") or {})
    text = dict(billing.get("text") or {})
    image = dict(billing.get("image") or {})
    audio = dict(billing.get("audio") or {})

    if "per_message_cost_bdt" in billing_settings:
        text["per_message_cost_bdt"] = _safe_float(billing_settings.get("per_message_cost_bdt"), default=0.0) or 0.0
    if "text_input_cost_per_million_bdt" in billing_settings:
        text["input_cost_per_million_bdt"] = _safe_float(billing_settings.get("text_input_cost_per_million_bdt"), default=0.0) or 0.0
    if "text_output_cost_per_million_bdt" in billing_settings:
        text["output_cost_per_million_bdt"] = _safe_float(billing_settings.get("text_output_cost_per_million_bdt"), default=0.0) or 0.0
    if "image_input_cost_per_million_bdt" in billing_settings:
        image["input_cost_per_million_bdt"] = _safe_float(billing_settings.get("image_input_cost_per_million_bdt"), default=0.0) or 0.0
    if "image_output_cost_per_million_bdt" in billing_settings:
        image["output_cost_per_million_bdt"] = _safe_float(billing_settings.get("image_output_cost_per_million_bdt"), default=0.0) or 0.0
    if "audio_input_cost_per_million_bdt" in billing_settings:
        audio["input_cost_per_million_bdt"] = _safe_float(billing_settings.get("audio_input_cost_per_million_bdt"), default=0.0) or 0.0
    if "audio_output_cost_per_million_bdt" in billing_settings:
        audio["output_cost_per_million_bdt"] = _safe_float(billing_settings.get("audio_output_cost_per_million_bdt"), default=0.0) or 0.0

    billing["text"] = text
    billing["image"] = image
    billing["audio"] = audio
    settings_json["billing"] = billing
    return settings_json


def serialize_brand_llm_settings(
    brand: models.Brand | None,
    *,
    include_secret: bool = False,
    settings: Settings | None = None,
    modality: str = "text",
) -> dict[str, Any]:
    runtime = resolve_llm_runtime_config(brand, settings=settings, modality=modality)
    return {
        "provider": runtime.provider,
        "provider_label": provider_label(runtime.provider),
        "model": runtime.model,
        "api_key": runtime.api_key if include_secret else None,
        "masked_api_key": mask_secret(runtime.api_key),
        "has_api_key": bool(runtime.api_key),
        "summary_model": runtime.summary_model,
        "embedding_model": runtime.embedding_model,
        "temperature": runtime.temperature,
        "top_p": runtime.top_p,
        "top_k": runtime.top_k,
        "max_output_tokens": runtime.max_output_tokens,
        "site_url": runtime.site_url,
        "app_name": runtime.app_name,
    }


def serialize_brand_billing_settings(brand: models.Brand | None) -> dict[str, float]:
    billing = extract_brand_billing_settings(brand)
    text = billing.get("text") if isinstance(billing.get("text"), dict) else {}
    image = billing.get("image") if isinstance(billing.get("image"), dict) else {}
    audio = billing.get("audio") if isinstance(billing.get("audio"), dict) else {}
    return {
        "per_message_cost_bdt": float(text.get("per_message_cost_bdt") or 0.0),
        "text_input_cost_per_million_bdt": float(text.get("input_cost_per_million_bdt") or 0.0),
        "text_output_cost_per_million_bdt": float(text.get("output_cost_per_million_bdt") or 0.0),
        "image_input_cost_per_million_bdt": float(image.get("input_cost_per_million_bdt") or 0.0),
        "image_output_cost_per_million_bdt": float(image.get("output_cost_per_million_bdt") or 0.0),
        "audio_input_cost_per_million_bdt": float(audio.get("input_cost_per_million_bdt") or 0.0),
        "audio_output_cost_per_million_bdt": float(audio.get("output_cost_per_million_bdt") or 0.0),
    }


def mask_secret(value: str | None) -> str | None:
    if not value:
        return None
    cleaned = value.strip()
    if len(cleaned) <= 8:
        return "*" * len(cleaned)
    return f"{cleaned[:4]}{'*' * max(4, len(cleaned) - 8)}{cleaned[-4:]}"


def _safe_float(value: Any, default: float | None = None) -> float | None:
    if value is None or value == "":
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _safe_int(value: Any, default: int | None = None) -> int | None:
    if value is None or value == "":
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _strip_or_none(value: Any) -> str | None:
    normalized = str(value or "").strip()
    return normalized or None
