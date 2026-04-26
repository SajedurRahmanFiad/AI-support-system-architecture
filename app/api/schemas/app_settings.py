from __future__ import annotations

from pydantic import BaseModel


class AppSettingsOut(BaseModel):
    main_system_prompt: str
    tone_name: str
    tone_instructions: str
    public_reply_guidelines: str


class AppSettingsUpdate(BaseModel):
    main_system_prompt: str
    tone_name: str | None = None
    tone_instructions: str | None = None
    public_reply_guidelines: str | None = None
