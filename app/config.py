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
    database_url: str = Field(
        default="sqlite+pysqlite:///./local.db",
        alias="DATABASE_URL",
    )
    platform_api_token: str = Field(default="change-this-platform-token", alias="PLATFORM_API_TOKEN")

    llm_provider: str = Field(default="gemini", alias="LLM_PROVIDER")
    gemini_api_key: str = Field(default="", alias="GEMINI_API_KEY")
    gemini_model: str = Field(default="gemini-2.0-flash", alias="GEMINI_MODEL")
    gemini_summary_model: str = Field(default="gemini-2.0-flash", alias="GEMINI_SUMMARY_MODEL")
    gemini_embedding_model: str = Field(default="gemini-embedding-001", alias="GEMINI_EMBEDDING_MODEL")

    knowledge_scan_limit: int = Field(default=400, alias="KNOWLEDGE_SCAN_LIMIT")
    knowledge_top_k: int = Field(default=5, alias="KNOWLEDGE_TOP_K")
    handoff_confidence_threshold: float = Field(default=0.55, alias="HANDOFF_CONFIDENCE_THRESHOLD")
    prompt_recent_message_limit: int = Field(default=12, alias="PROMPT_RECENT_MESSAGE_LIMIT")
    summary_trigger_message_count: int = Field(default=8, alias="SUMMARY_TRIGGER_MESSAGE_COUNT")
    max_upload_bytes: int = Field(default=20_000_000, alias="MAX_UPLOAD_BYTES")
    upload_dir: str = Field(default="storage/uploads", alias="UPLOAD_DIR")
    allowed_origins: str = Field(default="*", alias="ALLOWED_ORIGINS")

    default_timezone: str = Field(default="UTC", alias="DEFAULT_TIMEZONE")
    mock_llm_enabled_without_key: bool = Field(default=True, alias="MOCK_LLM_ENABLED_WITHOUT_KEY")

    @field_validator("debug", mode="before")
    @classmethod
    def normalize_debug(cls, value: object) -> bool:
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized in {"1", "true", "yes", "on", "debug", "development"}:
                return True
            if normalized in {"0", "false", "no", "off", "release", "production"}:
                return False
        return False

    @property
    def upload_path(self) -> Path:
        return Path(self.upload_dir)

    @property
    def cors_origins(self) -> list[str]:
        if self.allowed_origins.strip() == "*":
            return ["*"]
        return [item.strip() for item in self.allowed_origins.split(",") if item.strip()]


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
