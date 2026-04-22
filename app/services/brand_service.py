from __future__ import annotations

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import models
from app.security import generate_api_key, hash_api_key, verify_api_key

GLOBAL_BRAND_SLUG = "__global__"
GLOBAL_BRAND_NAME = "__Global Conversation Scope__"


def is_global_brand(brand: models.Brand | None) -> bool:
    return bool(brand and brand.slug == GLOBAL_BRAND_SLUG)


def get_global_brand(db: Session) -> models.Brand | None:
    return db.scalar(select(models.Brand).where(models.Brand.slug == GLOBAL_BRAND_SLUG))


def ensure_global_brand(db: Session) -> models.Brand:
    existing = get_global_brand(db)
    if existing:
        return existing

    brand = models.Brand(
        name=GLOBAL_BRAND_NAME,
        slug=GLOBAL_BRAND_SLUG,
        description="Internal global conversation-training scope.",
        default_language="bn-BD",
        tone_name="Global shared support examples",
        tone_instructions="",
        fallback_handoff_message="A human teammate will continue this conversation shortly.",
        public_reply_guidelines="",
        active=False,
        settings_json={"internal_scope": "global_knowledge"},
        api_key_hash=hash_api_key("internal-global-brand"),
    )
    db.add(brand)
    db.commit()
    db.refresh(brand)
    return brand


def create_brand(db: Session, payload: dict) -> tuple[models.Brand, str]:
    if payload["slug"] == GLOBAL_BRAND_SLUG:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="This brand slug is reserved.")

    existing = db.scalar(select(models.Brand).where(models.Brand.slug == payload["slug"]))
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Brand slug already exists.")

    api_key = generate_api_key("brand")
    brand = models.Brand(
        name=payload["name"],
        slug=payload["slug"],
        description=payload.get("description"),
        default_language=payload.get("default_language", "bn-BD"),
        tone_name=payload.get("tone_name", "Helpful sales assistant"),
        tone_instructions=payload.get("tone_instructions", ""),
        fallback_handoff_message=payload.get(
            "fallback_handoff_message",
            "A human teammate will continue this conversation shortly.",
        ),
        public_reply_guidelines=payload.get("public_reply_guidelines"),
        settings_json=payload.get("settings", {}),
        api_key_hash=hash_api_key(api_key),
    )
    db.add(brand)
    db.commit()
    db.refresh(brand)
    return brand, api_key


def get_brand_or_404(db: Session, brand_id: int) -> models.Brand:
    brand = db.scalar(select(models.Brand).where(models.Brand.id == brand_id, models.Brand.slug != GLOBAL_BRAND_SLUG))
    if not brand:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Brand not found.")
    return brand


def require_brand_access(
    db: Session,
    brand_id: int,
    brand_token: str | None,
    platform_token: str | None,
    expected_platform_token: str,
) -> models.Brand:
    brand = get_brand_or_404(db, brand_id)
    if platform_token and platform_token == expected_platform_token:
        return brand
    if not brand_token or not verify_api_key(brand_token, brand.api_key_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid brand access token.")
    return brand


def rotate_brand_key(db: Session, brand: models.Brand) -> str:
    api_key = generate_api_key("brand")
    brand.api_key_hash = hash_api_key(api_key)
    db.add(brand)
    db.commit()
    db.refresh(brand)
    return api_key
