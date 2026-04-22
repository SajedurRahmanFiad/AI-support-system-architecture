from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, field_validator


def _strip_or_none(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    return normalized or None


class FacebookPageBase(BaseModel):
    page_name: str
    page_id: str
    page_username: str | None = None
    app_id: str
    app_secret: str
    page_access_token: str
    verify_token: str
    active: bool = True
    automation_enabled: bool = True
    reply_to_messages: bool = True
    reply_to_comments: bool = False
    private_reply_to_comments: bool = False
    auto_hide_spam_comments: bool = False
    handoff_enabled: bool = True
    business_hours_only: bool = False
    reply_delay_seconds: int = 15
    allowed_reply_window_hours: int = 24
    default_language: str = "bn-BD"
    timezone: str = "Asia/Dhaka"
    live_server_label: str | None = None
    notes: str | None = None

    @field_validator(
        "page_name",
        "page_id",
        "app_id",
        "app_secret",
        "page_access_token",
        "verify_token",
        "default_language",
        "timezone",
        mode="before",
    )
    @classmethod
    def validate_required_strings(cls, value: object) -> str:
        normalized = str(value or "").strip()
        if normalized == "":
            raise ValueError("This field is required.")
        return normalized

    @field_validator("page_username", "live_server_label", "notes", mode="before")
    @classmethod
    def normalize_optional_strings(cls, value: object) -> str | None:
        return _strip_or_none(None if value is None else str(value))


class FacebookPageCreate(FacebookPageBase):
    brand_id: int


class FacebookPageUpdate(BaseModel):
    brand_id: int | None = None
    page_name: str | None = None
    page_id: str | None = None
    page_username: str | None = None
    app_id: str | None = None
    app_secret: str | None = None
    page_access_token: str | None = None
    verify_token: str | None = None
    active: bool | None = None
    automation_enabled: bool | None = None
    reply_to_messages: bool | None = None
    reply_to_comments: bool | None = None
    private_reply_to_comments: bool | None = None
    auto_hide_spam_comments: bool | None = None
    handoff_enabled: bool | None = None
    business_hours_only: bool | None = None
    reply_delay_seconds: int | None = None
    allowed_reply_window_hours: int | None = None
    default_language: str | None = None
    timezone: str | None = None
    live_server_label: str | None = None
    notes: str | None = None

    @field_validator(
        "page_name",
        "page_id",
        "app_id",
        "app_secret",
        "page_access_token",
        "verify_token",
        "default_language",
        "timezone",
        mode="before",
    )
    @classmethod
    def normalize_required_update_strings(cls, value: object) -> str | None:
        if value is None:
            return None
        normalized = str(value).strip()
        if normalized == "":
            raise ValueError("This field cannot be empty.")
        return normalized

    @field_validator("page_username", "live_server_label", "notes", mode="before")
    @classmethod
    def normalize_optional_update_strings(cls, value: object) -> str | None:
        return _strip_or_none(None if value is None else str(value))


class FacebookCredentialStatusOut(BaseModel):
    has_app_secret: bool
    has_page_access_token: bool
    has_verify_token: bool
    ready: bool


class FacebookPageSummaryOut(BaseModel):
    id: int
    brand_id: int
    brand_name: str
    brand_slug: str
    page_name: str
    page_id: str
    page_username: str | None
    app_id: str
    active: bool
    automation_enabled: bool
    reply_to_messages: bool
    reply_to_comments: bool
    private_reply_to_comments: bool
    auto_hide_spam_comments: bool
    handoff_enabled: bool
    business_hours_only: bool
    reply_delay_seconds: int
    allowed_reply_window_hours: int
    default_language: str
    timezone: str
    live_server_label: str | None
    notes: str | None
    credential_status: FacebookCredentialStatusOut
    created_at: datetime
    updated_at: datetime


class FacebookPageOut(FacebookPageSummaryOut):
    app_secret: str
    page_access_token: str
    verify_token: str
