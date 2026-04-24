from __future__ import annotations

from pydantic import BaseModel


class AppSettingsOut(BaseModel):
    main_system_prompt: str


class AppSettingsUpdate(BaseModel):
    main_system_prompt: str

