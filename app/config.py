from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_name: str = Field(default="B2B AI Support API", alias="APP_NAME")
    app_env: str = Field(default="development", alias="APP_ENV")
    debug: bool = Field(default=False, alias="DEBUG")
    root_path: str = Field(default="", alias="ROOT_PATH")
    database_url: str = Field(
        default="sqlite+pysqlite:///./local.db",
        alias="DATABASE_URL",
    )
    platform_api_token: str = Field(default="change-this-platform-token", alias="PLATFORM_API_TOKEN")

    llm_provider: str = Field(default="gemini", alias="LLM_PROVIDER")
    gemini_api_key: str = Field(default="", alias="GEMINI_API_KEY")
    gemini_model: str = Field(default="gemini-2.5-flash", alias="GEMINI_MODEL")
    gemini_summary_model: str = Field(default="gemini-2.5-flash", alias="GEMINI_SUMMARY_MODEL")
    gemini_embedding_model: str = Field(default="gemini-embedding-2-preview", alias="GEMINI_EMBEDDING_MODEL")
    groq_api_key: str = Field(default="", alias="GROQ_API_KEY")
    groq_model: str = Field(default="llama-3.3-70b-versatile", alias="GROQ_MODEL")
    openai_api_key: str = Field(default="", alias="OPENAI_API_KEY")
    openai_model: str = Field(default="gpt-4.1-mini", alias="OPENAI_MODEL")
    openai_summary_model: str = Field(default="gpt-4.1-mini", alias="OPENAI_SUMMARY_MODEL")
    openai_embedding_model: str = Field(default="text-embedding-3-small", alias="OPENAI_EMBEDDING_MODEL")
    openrouter_api_key: str = Field(default="", alias="OPENROUTER_API_KEY")
    openrouter_model: str = Field(default="openai/gpt-4.1-mini", alias="OPENROUTER_MODEL")
    openrouter_summary_model: str = Field(default="openai/gpt-4.1-mini", alias="OPENROUTER_SUMMARY_MODEL")
    openrouter_embedding_model: str = Field(default="openai/text-embedding-3-small", alias="OPENROUTER_EMBEDDING_MODEL")
    openrouter_site_url: str = Field(default="", alias="OPENROUTER_SITE_URL")
    openrouter_app_name: str = Field(default="", alias="OPENROUTER_APP_NAME")
    speech_provider: str = Field(default="gemini", alias="SPEECH_PROVIDER")
    google_cloud_project_id: str = Field(default="", alias="GOOGLE_CLOUD_PROJECT_ID")
    speech_primary_language: str = Field(default="bn-BD", alias="SPEECH_PRIMARY_LANGUAGE")
    speech_alt_languages: str = Field(default="bn-BD,en-US,en-GB,hi-IN", alias="SPEECH_ALT_LANGUAGES")
    speech_low_confidence_threshold: float = Field(default=0.65, alias="SPEECH_LOW_CONFIDENCE_THRESHOLD")
    gemini_inline_audio_max_bytes: int = Field(default=8_000_000, alias="GEMINI_INLINE_AUDIO_MAX_BYTES")
    force_bangla_reply_by_default: bool = Field(default=True, alias="FORCE_BANGLA_REPLY_BY_DEFAULT")
    unclear_audio_reply_bn: str = Field(
        default="দুঃখিত, ভয়েস মেসেজটি পরিষ্কারভাবে বুঝতে পারিনি। দয়া করে ছোট করে আবার ভয়েস দিন, অথবা একটি টেক্সট মেসেজ পাঠান।",
        alias="UNCLEAR_AUDIO_REPLY_BN",
    )
    unclear_audio_reply_en: str = Field(
        default="Sorry, I could not understand the voice note clearly. Please send a shorter voice note or a text message.",
        alias="UNCLEAR_AUDIO_REPLY_EN",
    )

    knowledge_scan_limit: int = Field(default=400, alias="KNOWLEDGE_SCAN_LIMIT")
    knowledge_top_k: int = Field(default=5, alias="KNOWLEDGE_TOP_K")
    handoff_confidence_threshold: float = Field(default=0.55, alias="HANDOFF_CONFIDENCE_THRESHOLD")
    prompt_recent_message_limit: int = Field(default=12, alias="PROMPT_RECENT_MESSAGE_LIMIT")
    summary_trigger_message_count: int = Field(default=8, alias="SUMMARY_TRIGGER_MESSAGE_COUNT")
    max_upload_bytes: int = Field(default=20_000_000, alias="MAX_UPLOAD_BYTES")
    upload_dir: str = Field(default="storage/uploads", alias="UPLOAD_DIR")
    allowed_origins: str = Field(default="*", alias="ALLOWED_ORIGINS")

    default_timezone: str = Field(default="Asia/Dhaka", alias="DEFAULT_TIMEZONE")
    mock_llm_enabled_without_key: bool = Field(default=True, alias="MOCK_LLM_ENABLED_WITHOUT_KEY")
    facebook_credential_validation_enabled: bool = Field(
        default=True,
        alias="FACEBOOK_CREDENTIAL_VALIDATION_ENABLED",
    )
    facebook_webhook_async_enabled: bool = Field(default=False, alias="FACEBOOK_WEBHOOK_ASYNC_ENABLED")
    facebook_message_batching_enabled: bool = Field(default=True, alias="FACEBOOK_MESSAGE_BATCHING_ENABLED")
    facebook_message_batch_window_seconds: int = Field(default=5, alias="FACEBOOK_MESSAGE_BATCH_WINDOW_SECONDS")
    db_pool_size: int = Field(default=20, alias="DB_POOL_SIZE")
    db_max_overflow: int = Field(default=40, alias="DB_MAX_OVERFLOW")
    db_pool_recycle: int = Field(default=1800, alias="DB_POOL_RECYCLE")
    db_pool_timeout: int = Field(default=30, alias="DB_POOL_TIMEOUT")
    message_processing_async_default: bool = Field(default=False, alias="MESSAGE_PROCESSING_ASYNC_DEFAULT")
    job_runner_enabled: bool = Field(default=True, alias="JOB_RUNNER_ENABLED")
    job_runner_poll_interval_seconds: float = Field(default=0.5, alias="JOB_RUNNER_POLL_INTERVAL_SECONDS")
    job_runner_batch_size: int = Field(default=24, alias="JOB_RUNNER_BATCH_SIZE")
    job_runner_max_concurrency: int = Field(default=6, alias="JOB_RUNNER_MAX_CONCURRENCY")
    job_retry_limit: int = Field(default=3, alias="JOB_RETRY_LIMIT")
    job_retry_delay_seconds: int = Field(default=5, alias="JOB_RETRY_DELAY_SECONDS")

    @field_validator("debug", mode="before")
    @classmethod
    def normalize_debug(cls, value: object) -> bool:
        return cls._parse_bool(value, default=False)

    @field_validator(
        "mock_llm_enabled_without_key",
        "facebook_credential_validation_enabled",
        "job_runner_enabled",
        "facebook_message_batching_enabled",
        mode="before",
    )
    @classmethod
    def normalize_boolean_settings(cls, value: object) -> bool:
        return cls._parse_bool(value, default=True)

    @field_validator("message_processing_async_default", "facebook_webhook_async_enabled", mode="before")
    @classmethod
    def normalize_false_default_boolean_settings(cls, value: object) -> bool:
        return cls._parse_bool(value, default=False)

    @field_validator("root_path", mode="before")
    @classmethod
    def normalize_root_path(cls, value: object) -> str:
        if value is None:
            return ""
        normalized = str(value).strip()
        if not normalized or normalized == "/":
            return ""
        if not normalized.startswith("/"):
            normalized = f"/{normalized}"
        return normalized.rstrip("/")

    @property
    def upload_path(self) -> Path:
        return Path(self.upload_dir)

    @property
    def cors_origins(self) -> list[str]:
        if self.allowed_origins.strip() == "*":
            return ["*"]
        return [item.strip() for item in self.allowed_origins.split(",") if item.strip()]

    @property
    def speech_alt_language_list(self) -> list[str]:
        return [item.strip() for item in self.speech_alt_languages.split(",") if item.strip()]

    @staticmethod
    def _parse_bool(value: object, *, default: bool) -> bool:
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized in {"1", "true", "yes", "on", "debug", "development"}:
                return True
            if normalized in {"0", "false", "no", "off", "release", "production"}:
                return False
        return default


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
