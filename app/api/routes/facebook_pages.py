from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app import models
from app.api.deps import DbSession, require_platform_access
from app.api.schemas.facebook_pages import (
    FacebookCredentialStatusOut,
    FacebookPageCreate,
    FacebookPageOut,
    FacebookPageSummaryOut,
    FacebookPageUpdate,
)
from app.services.brand_service import get_brand_or_404
from app.services.facebook_credentials import FacebookPageCredentialValidator
from app.config import get_settings

router = APIRouter(prefix="/v1/facebook-pages", dependencies=[Depends(require_platform_access)])


def _page_query():
    return select(models.FacebookPageAutomation).options(selectinload(models.FacebookPageAutomation.brand))


def _get_page_or_404(db: DbSession, page_id: int) -> models.FacebookPageAutomation:
    page = db.scalar(_page_query().where(models.FacebookPageAutomation.id == page_id))
    if not page:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Facebook page automation config not found.")
    return page


def _ensure_unique_page_id(
    db: DbSession,
    page_id_value: str,
    existing_id: int | None = None,
) -> None:
    existing = db.scalar(select(models.FacebookPageAutomation).where(models.FacebookPageAutomation.page_id == page_id_value))
    if existing and existing.id != existing_id:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="A Facebook page with this Page ID already exists.")


def _credential_status(page: models.FacebookPageAutomation) -> FacebookCredentialStatusOut:
    has_app_secret = bool(page.app_secret)
    has_page_access_token = bool(page.page_access_token)
    has_verify_token = bool(page.verify_token)
    return FacebookCredentialStatusOut(
        has_app_secret=has_app_secret,
        has_page_access_token=has_page_access_token,
        has_verify_token=has_verify_token,
        ready=has_app_secret and has_page_access_token and has_verify_token,
    )


def _serialize_summary(page: models.FacebookPageAutomation) -> FacebookPageSummaryOut:
    if page.brand is None:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Facebook page is missing its brand link.")

    return FacebookPageSummaryOut(
        id=page.id,
        brand_id=page.brand_id,
        brand_name=page.brand.name,
        brand_slug=page.brand.slug,
        page_name=page.page_name,
        page_id=page.page_id,
        page_username=page.page_username,
        app_id=page.app_id,
        active=page.active,
        automation_enabled=page.automation_enabled,
        reply_to_messages=page.reply_to_messages,
        reply_to_comments=page.reply_to_comments,
        private_reply_to_comments=page.private_reply_to_comments,
        auto_hide_spam_comments=page.auto_hide_spam_comments,
        handoff_enabled=page.handoff_enabled,
        business_hours_only=page.business_hours_only,
        reply_delay_seconds=page.reply_delay_seconds,
        allowed_reply_window_hours=page.allowed_reply_window_hours,
        default_language=page.default_language,
        timezone=page.timezone,
        live_server_label=page.live_server_label,
        notes=page.notes,
        credential_status=_credential_status(page),
        created_at=page.created_at,
        updated_at=page.updated_at,
    )


def _serialize_detail(page: models.FacebookPageAutomation) -> FacebookPageOut:
    base = _serialize_summary(page).model_dump()
    return FacebookPageOut(
        **base,
        app_secret=page.app_secret,
        page_access_token=page.page_access_token,
        verify_token=page.verify_token,
    )


@router.get("", response_model=list[FacebookPageSummaryOut])
def list_facebook_pages(
    db: DbSession,
    brand_id: int | None = Query(default=None),
) -> list[FacebookPageSummaryOut]:
    query = _page_query().order_by(models.FacebookPageAutomation.updated_at.desc(), models.FacebookPageAutomation.created_at.desc())
    if brand_id is not None:
        query = query.where(models.FacebookPageAutomation.brand_id == brand_id)
    pages = list(db.scalars(query))
    return [_serialize_summary(page) for page in pages]


@router.post("", response_model=FacebookPageOut)
def create_facebook_page(payload: FacebookPageCreate, db: DbSession) -> FacebookPageOut:
    get_brand_or_404(db, payload.brand_id)
    _ensure_unique_page_id(db, payload.page_id)
    _validate_credentials_on_save(
        app_id=payload.app_id,
        app_secret=payload.app_secret,
        page_id=payload.page_id,
        page_access_token=payload.page_access_token,
    )
    page = models.FacebookPageAutomation(**payload.model_dump())
    db.add(page)
    db.commit()
    db.refresh(page)
    page = _get_page_or_404(db, page.id)
    return _serialize_detail(page)


@router.get("/{page_id}", response_model=FacebookPageOut)
def get_facebook_page(page_id: int, db: DbSession) -> FacebookPageOut:
    page = _get_page_or_404(db, page_id)
    return _serialize_detail(page)


@router.patch("/{page_id}", response_model=FacebookPageOut)
def update_facebook_page(page_id: int, payload: FacebookPageUpdate, db: DbSession) -> FacebookPageOut:
    page = _get_page_or_404(db, page_id)
    data = payload.model_dump(exclude_unset=True)

    next_brand_id = data.get("brand_id")
    if next_brand_id is not None:
        get_brand_or_404(db, next_brand_id)

    next_page_id = data.get("page_id")
    if next_page_id is not None:
        _ensure_unique_page_id(db, next_page_id, existing_id=page.id)

    if {"page_id", "app_id", "app_secret", "page_access_token"} & data.keys():
        _validate_credentials_on_save(
            app_id=str(data.get("app_id", page.app_id)),
            app_secret=str(data.get("app_secret", page.app_secret)),
            page_id=str(data.get("page_id", page.page_id)),
            page_access_token=str(data.get("page_access_token", page.page_access_token)),
        )

    for field, value in data.items():
        setattr(page, field, value)

    db.add(page)
    db.commit()
    db.refresh(page)
    page = _get_page_or_404(db, page.id)
    return _serialize_detail(page)


@router.delete("/{page_id}")
def delete_facebook_page(page_id: int, db: DbSession) -> dict[str, str]:
    page = _get_page_or_404(db, page_id)
    db.delete(page)
    db.commit()
    return {"status": "deleted"}


def _validate_credentials_on_save(
    *,
    app_id: str,
    app_secret: str,
    page_id: str,
    page_access_token: str,
) -> None:
    settings = get_settings()
    if not settings.facebook_credential_validation_enabled:
        return

    FacebookPageCredentialValidator().validate_page_access_token(
        app_id=app_id,
        app_secret=app_secret,
        page_id=page_id,
        page_access_token=page_access_token,
    )
