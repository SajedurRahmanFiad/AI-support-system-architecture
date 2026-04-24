from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.services.llm.runtime import (
    merge_brand_billing_settings,
    merge_brand_llm_settings,
    merge_brand_processing_settings,
    serialize_brand_billing_settings,
    serialize_brand_llm_settings,
)


class BrandLLMSettingsInput(BaseModel):
    provider: str
    model: str | None = None
    api_key: str | None = None
    summary_model: str | None = None
    embedding_model: str | None = None
    temperature: float | None = None
    top_p: float | None = None
    top_k: int | None = None
    max_output_tokens: int | None = None
    site_url: str | None = None
    app_name: str | None = None

    @field_validator("provider", mode="before")
    @classmethod
    def normalize_provider(cls, value: object) -> str:
        normalized = str(value or "").strip().lower()
        aliases = {
            "google": "gemini",
            "gemini": "gemini",
            "openai": "openai",
            "groq": "groq",
            "openrouter": "openrouter",
            "mock": "mock",
        }
        if normalized not in aliases:
            raise ValueError("Unsupported LLM provider.")
        return aliases[normalized]

    @field_validator(
        "model",
        "api_key",
        "summary_model",
        "embedding_model",
        "site_url",
        "app_name",
        mode="before",
    )
    @classmethod
    def strip_text_values(cls, value: object) -> str | None:
        normalized = str(value or "").strip()
        return normalized or None

    @model_validator(mode="after")
    def validate_required_fields(self) -> "BrandLLMSettingsInput":
        if self.provider != "mock" and not self.api_key:
            raise ValueError("API key is required for this provider.")
        if self.provider != "mock" and not self.model:
            raise ValueError("Model name is required for this provider.")
        return self


class BrandLLMSettingsOut(BaseModel):
    provider: str
    provider_label: str
    model: str
    api_key: str | None = None
    masked_api_key: str | None = None
    has_api_key: bool = False
    summary_model: str | None = None
    embedding_model: str | None = None
    temperature: float | None = None
    top_p: float | None = None
    top_k: int | None = None
    max_output_tokens: int | None = None
    site_url: str | None = None
    app_name: str | None = None


class BrandBillingSettingsInput(BaseModel):
    per_message_cost_bdt: float | None = None
    text_input_cost_per_million_bdt: float | None = None
    text_output_cost_per_million_bdt: float | None = None
    image_input_cost_per_million_bdt: float | None = None
    image_output_cost_per_million_bdt: float | None = None
    audio_input_cost_per_million_bdt: float | None = None
    audio_output_cost_per_million_bdt: float | None = None


class BrandBillingSettingsOut(BaseModel):
    per_message_cost_bdt: float = 0.0
    text_input_cost_per_million_bdt: float = 0.0
    text_output_cost_per_million_bdt: float = 0.0
    image_input_cost_per_million_bdt: float = 0.0
    image_output_cost_per_million_bdt: float = 0.0
    audio_input_cost_per_million_bdt: float = 0.0
    audio_output_cost_per_million_bdt: float = 0.0


class BrandCreate(BaseModel):
    name: str
    slug: str
    description: str | None = None
    default_language: str = "bn-BD"
    tone_name: str = "Helpful sales assistant"
    tone_instructions: str = ""
    fallback_handoff_message: str = "A human teammate will continue this conversation shortly."
    public_reply_guidelines: str | None = None
    settings: dict[str, Any] = Field(default_factory=dict)
    llm_settings: BrandLLMSettingsInput | None = None
    text_processing: BrandLLMSettingsInput | None = None
    image_processing: BrandLLMSettingsInput | None = None
    audio_processing: BrandLLMSettingsInput | None = None
    billing_settings: BrandBillingSettingsInput | None = None


class BrandUpdate(BaseModel):
    name: str | None = None
    slug: str | None = None
    description: str | None = None
    default_language: str | None = None
    tone_name: str | None = None
    tone_instructions: str | None = None
    fallback_handoff_message: str | None = None
    public_reply_guidelines: str | None = None
    active: bool | None = None
    settings: dict[str, Any] | None = None
    llm_settings: BrandLLMSettingsInput | None = None
    text_processing: BrandLLMSettingsInput | None = None
    image_processing: BrandLLMSettingsInput | None = None
    audio_processing: BrandLLMSettingsInput | None = None
    billing_settings: BrandBillingSettingsInput | None = None


class BrandPromptConfigUpdate(BaseModel):
    default_language: str | None = None
    tone_name: str | None = None
    tone_instructions: str | None = None
    fallback_handoff_message: str | None = None
    public_reply_guidelines: str | None = None


class BrandRuleCreate(BaseModel):
    category: str = "general"
    title: str
    content: str
    handoff_on_match: bool = False
    priority: int = 100


class BrandRuleUpdate(BaseModel):
    category: str | None = None
    title: str | None = None
    content: str | None = None
    handoff_on_match: bool | None = None
    priority: int | None = None


class StyleExampleCreate(BaseModel):
    title: str
    trigger_text: str
    ideal_reply: str
    notes: str | None = None
    priority: int = 100


class StyleExampleUpdate(BaseModel):
    title: str | None = None
    trigger_text: str | None = None
    ideal_reply: str | None = None
    notes: str | None = None
    priority: int | None = None


class BrandRuleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    category: str
    title: str
    content: str
    handoff_on_match: bool
    priority: int
    created_at: datetime


class StyleExampleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    trigger_text: str
    ideal_reply: str
    notes: str | None
    priority: int
    created_at: datetime


class BrandOut(BaseModel):
    id: int
    name: str
    slug: str
    description: str | None
    default_language: str
    tone_name: str
    tone_instructions: str
    fallback_handoff_message: str
    public_reply_guidelines: str | None
    active: bool
    llm_settings: BrandLLMSettingsOut | None = None
    text_processing: BrandLLMSettingsOut | None = None
    image_processing: BrandLLMSettingsOut | None = None
    audio_processing: BrandLLMSettingsOut | None = None
    billing_settings: BrandBillingSettingsOut = Field(default_factory=BrandBillingSettingsOut)
    created_at: datetime
    updated_at: datetime


class BrandWithSecretOut(BrandOut):
    api_key: str


class BrandPromptConfigOut(BaseModel):
    brand_id: int
    brand_name: str
    slug: str
    default_language: str
    tone_name: str
    tone_instructions: str
    fallback_handoff_message: str
    public_reply_guidelines: str | None
    updated_at: datetime


def serialize_brand_output(brand: Any, *, include_llm_secret: bool = False) -> BrandOut:
    return BrandOut(
        id=brand.id,
        name=brand.name,
        slug=brand.slug,
        description=brand.description,
        default_language=brand.default_language,
        tone_name=brand.tone_name,
        tone_instructions=brand.tone_instructions,
        fallback_handoff_message=brand.fallback_handoff_message,
        public_reply_guidelines=brand.public_reply_guidelines,
        active=brand.active,
        llm_settings=BrandLLMSettingsOut(**serialize_brand_llm_settings(brand, include_secret=include_llm_secret, modality="text")),
        text_processing=BrandLLMSettingsOut(**serialize_brand_llm_settings(brand, include_secret=include_llm_secret, modality="text")),
        image_processing=BrandLLMSettingsOut(**serialize_brand_llm_settings(brand, include_secret=include_llm_secret, modality="image")),
        audio_processing=BrandLLMSettingsOut(**serialize_brand_llm_settings(brand, include_secret=include_llm_secret, modality="audio")),
        billing_settings=BrandBillingSettingsOut(**serialize_brand_billing_settings(brand)),
        created_at=brand.created_at,
        updated_at=brand.updated_at,
    )


def apply_brand_payload(brand: Any, payload: BrandCreate | BrandUpdate) -> None:
    data = payload.model_dump(exclude_unset=True)
    llm_settings = data.pop("llm_settings", None)
    text_processing = data.pop("text_processing", None)
    image_processing = data.pop("image_processing", None)
    audio_processing = data.pop("audio_processing", None)
    billing_settings = data.pop("billing_settings", None)
    settings_json = data.pop("settings", None)

    for field, value in data.items():
        setattr(brand, field, value)

    merged_settings = brand.settings_json if settings_json is None else settings_json
    if llm_settings is not None:
        merged_settings = merge_brand_llm_settings(merged_settings, llm_settings)
    if text_processing is not None:
        merged_settings = merge_brand_processing_settings(merged_settings, "text", text_processing)
    if image_processing is not None:
        merged_settings = merge_brand_processing_settings(merged_settings, "image", image_processing)
    if audio_processing is not None:
        merged_settings = merge_brand_processing_settings(merged_settings, "audio", audio_processing)
    if billing_settings is not None:
        merged_settings = merge_brand_billing_settings(merged_settings, billing_settings)
    if (
        settings_json is not None
        or llm_settings is not None
        or text_processing is not None
        or image_processing is not None
        or audio_processing is not None
        or billing_settings is not None
    ):
        setattr(brand, "settings_json", merged_settings)
