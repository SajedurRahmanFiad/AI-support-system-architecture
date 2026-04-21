from fastapi import APIRouter, Depends, Security
from sqlalchemy.orm import Session

from app.api.deps import brand_token_header, platform_token_header
from app.api.schemas.brands import BrandPromptConfigOut, BrandPromptConfigUpdate
from app.config import get_settings
from app.database import get_db
from app.services.brand_service import require_brand_access

router = APIRouter(prefix="/brands")


def _serialize_prompt_config(brand) -> BrandPromptConfigOut:
    return BrandPromptConfigOut(
        brand_id=brand.id,
        brand_name=brand.name,
        slug=brand.slug,
        default_language=brand.default_language,
        tone_name=brand.tone_name,
        tone_instructions=brand.tone_instructions,
        fallback_handoff_message=brand.fallback_handoff_message,
        public_reply_guidelines=brand.public_reply_guidelines,
        updated_at=brand.updated_at,
    )


@router.get("/{brand_id}/prompt-config", response_model=BrandPromptConfigOut)
def get_prompt_config(
    brand_id: int,
    db: Session = Depends(get_db),
    brand_token: str | None = Security(brand_token_header),
    platform_token: str | None = Security(platform_token_header),
) -> BrandPromptConfigOut:
    brand = require_brand_access(db, brand_id, brand_token, platform_token, get_settings().platform_api_token)
    return _serialize_prompt_config(brand)


@router.patch("/{brand_id}/prompt-config", response_model=BrandPromptConfigOut)
def update_prompt_config(
    brand_id: int,
    payload: BrandPromptConfigUpdate,
    db: Session = Depends(get_db),
    brand_token: str | None = Security(brand_token_header),
    platform_token: str | None = Security(platform_token_header),
) -> BrandPromptConfigOut:
    brand = require_brand_access(db, brand_id, brand_token, platform_token, get_settings().platform_api_token)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(brand, field, value)
    db.add(brand)
    db.commit()
    db.refresh(brand)
    return _serialize_prompt_config(brand)
