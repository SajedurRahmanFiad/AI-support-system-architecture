from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.deps import DbSession, require_platform_access
from app.api.schemas.app_settings import AppSettingsOut, AppSettingsUpdate
from app.services.app_settings import MAIN_SYSTEM_PROMPT_KEY, get_main_system_prompt, upsert_setting_value

router = APIRouter(prefix="/v1/app-settings", dependencies=[Depends(require_platform_access)])


@router.get("", response_model=AppSettingsOut)
def get_app_settings(db: DbSession) -> AppSettingsOut:
    return AppSettingsOut(main_system_prompt=get_main_system_prompt(db))


@router.patch("", response_model=AppSettingsOut)
def update_app_settings(payload: AppSettingsUpdate, db: DbSession) -> AppSettingsOut:
    upsert_setting_value(
        db,
        MAIN_SYSTEM_PROMPT_KEY,
        {"text": payload.main_system_prompt},
    )
    return AppSettingsOut(main_system_prompt=get_main_system_prompt(db))

