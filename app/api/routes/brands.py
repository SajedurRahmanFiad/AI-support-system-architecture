from fastapi import APIRouter, Depends
from sqlalchemy import select

from app import models
from app.api.deps import DbSession, require_platform_access
from app.api.schemas.brands import (
    BrandCreate,
    BrandOut,
    BrandRuleCreate,
    BrandRuleOut,
    BrandUpdate,
    BrandWithSecretOut,
    StyleExampleCreate,
    StyleExampleOut,
)
from app.services.brand_service import create_brand, get_brand_or_404, rotate_brand_key

router = APIRouter(prefix="/v1/brands", dependencies=[Depends(require_platform_access)])


@router.get("", response_model=list[BrandOut])
def list_brands(db: DbSession) -> list[models.Brand]:
    return list(db.scalars(select(models.Brand).order_by(models.Brand.created_at.desc())))


@router.post("", response_model=BrandWithSecretOut)
def create_brand_route(payload: BrandCreate, db: DbSession) -> BrandWithSecretOut:
    brand, api_key = create_brand(db, payload.model_dump())
    base = BrandOut.model_validate(brand).model_dump()
    return BrandWithSecretOut(**base, api_key=api_key)


@router.get("/{brand_id}", response_model=BrandOut)
def get_brand(brand_id: int, db: DbSession) -> models.Brand:
    return get_brand_or_404(db, brand_id)


@router.patch("/{brand_id}", response_model=BrandOut)
def update_brand(brand_id: int, payload: BrandUpdate, db: DbSession) -> models.Brand:
    brand = get_brand_or_404(db, brand_id)
    data = payload.model_dump(exclude_unset=True)
    for field, value in data.items():
        if field == "settings":
            setattr(brand, "settings_json", value)
        else:
            setattr(brand, field, value)
    db.add(brand)
    db.commit()
    db.refresh(brand)
    return brand


@router.post("/{brand_id}/reset-api-key")
def reset_brand_key(brand_id: int, db: DbSession) -> dict[str, str]:
    brand = get_brand_or_404(db, brand_id)
    api_key = rotate_brand_key(db, brand)
    return {"api_key": api_key}


@router.get("/{brand_id}/rules", response_model=list[BrandRuleOut])
def list_rules(brand_id: int, db: DbSession) -> list[models.BrandRule]:
    get_brand_or_404(db, brand_id)
    return list(
        db.scalars(
            select(models.BrandRule)
            .where(models.BrandRule.brand_id == brand_id)
            .order_by(models.BrandRule.priority.asc(), models.BrandRule.created_at.asc())
        )
    )


@router.post("/{brand_id}/rules", response_model=BrandRuleOut)
def create_rule(brand_id: int, payload: BrandRuleCreate, db: DbSession) -> models.BrandRule:
    get_brand_or_404(db, brand_id)
    rule = models.BrandRule(brand_id=brand_id, **payload.model_dump())
    db.add(rule)
    db.commit()
    db.refresh(rule)
    return rule


@router.get("/{brand_id}/style-examples", response_model=list[StyleExampleOut])
def list_style_examples(brand_id: int, db: DbSession) -> list[models.StyleExample]:
    get_brand_or_404(db, brand_id)
    return list(
        db.scalars(
            select(models.StyleExample)
            .where(models.StyleExample.brand_id == brand_id)
            .order_by(models.StyleExample.priority.asc(), models.StyleExample.created_at.asc())
        )
    )


@router.post("/{brand_id}/style-examples", response_model=StyleExampleOut)
def create_style_example(brand_id: int, payload: StyleExampleCreate, db: DbSession) -> models.StyleExample:
    get_brand_or_404(db, brand_id)
    row = models.StyleExample(brand_id=brand_id, **payload.model_dump())
    db.add(row)
    db.commit()
    db.refresh(row)
    return row
