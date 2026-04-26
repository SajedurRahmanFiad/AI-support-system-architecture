from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.deps import DbSession, require_platform_access
from app.api.schemas.app_settings import AppSettingsOut, AppSettingsUpdate
from app.services.app_settings import (
    GLOBAL_REPLY_CONFIG_KEY,
    MAIN_SYSTEM_PROMPT_KEY,
    get_global_reply_config,
    get_main_system_prompt,
    upsert_setting_value,
)

router = APIRouter(prefix="/v1/app-settings", dependencies=[Depends(require_platform_access)])


@router.get("", response_model=AppSettingsOut)
def get_app_settings(db: DbSession) -> AppSettingsOut:
    reply_config = get_global_reply_config(db)
    return AppSettingsOut(
        main_system_prompt=get_main_system_prompt(db),
        tone_name=reply_config["tone_name"],
        tone_instructions=reply_config["tone_instructions"],
        public_reply_guidelines=reply_config["public_reply_guidelines"],
    )


@router.patch("", response_model=AppSettingsOut)
def update_app_settings(payload: AppSettingsUpdate, db: DbSession) -> AppSettingsOut:
    current_reply_config = get_global_reply_config(db)
    upsert_setting_value(
        db,
        MAIN_SYSTEM_PROMPT_KEY,
        {"text": payload.main_system_prompt},
    )
    upsert_setting_value(
        db,
        GLOBAL_REPLY_CONFIG_KEY,
        {
            "tone_name": payload.tone_name if payload.tone_name is not None else current_reply_config["tone_name"],
            "tone_instructions": payload.tone_instructions if payload.tone_instructions is not None else current_reply_config["tone_instructions"],
            "public_reply_guidelines": payload.public_reply_guidelines
            if payload.public_reply_guidelines is not None
            else current_reply_config["public_reply_guidelines"],
        },
    )
    reply_config = get_global_reply_config(db)
    return AppSettingsOut(
        main_system_prompt=get_main_system_prompt(db),
        tone_name=reply_config["tone_name"],
        tone_instructions=reply_config["tone_instructions"],
        public_reply_guidelines=reply_config["public_reply_guidelines"],
    )
