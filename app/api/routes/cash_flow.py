from __future__ import annotations

from collections import defaultdict

from fastapi import APIRouter, Depends
from sqlalchemy import select

from app import models
from app.api.deps import DbSession, require_platform_access
from app.api.schemas.cash_flow import (
    CashFlowBrandSummaryOut,
    CashFlowOverviewOut,
    CashFlowPaymentCreate,
    CashFlowPaymentOut,
    CashFlowTotalsOut,
)
from app.services.billing import resolve_period_bounds
from app.services.brand_service import GLOBAL_BRAND_SLUG

router = APIRouter(prefix="/v1/cash-flow", dependencies=[Depends(require_platform_access)])


@router.get("/overview", response_model=CashFlowOverviewOut)
def get_cash_flow_overview(
    db: DbSession,
    brand_id: int | None = None,
    period: str = "month",
    custom_date: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
) -> CashFlowOverviewOut:
    start_at, end_at = resolve_period_bounds(
        period,
        custom_date=custom_date,
        start_date=start_date,
        end_date=end_date,
    )

    brand_statement = (
        select(models.Brand)
        .where(models.Brand.slug != GLOBAL_BRAND_SLUG)
        .order_by(models.Brand.name.asc())
    )
    if brand_id is not None:
        brand_statement = brand_statement.where(models.Brand.id == brand_id)
    brands = list(db.scalars(brand_statement))
    brand_ids = [brand.id for brand in brands]

    usage_statement = select(models.UsageRecord)
    payment_statement = select(models.BrandPayment)
    if brand_ids:
        usage_statement = usage_statement.where(models.UsageRecord.brand_id.in_(brand_ids))
        payment_statement = payment_statement.where(models.BrandPayment.brand_id.in_(brand_ids))

    usage_rows = list(
        db.scalars(
            usage_statement.where(
                models.UsageRecord.occurred_at >= start_at,
                models.UsageRecord.occurred_at < end_at,
            )
        )
    )
    payment_rows = list(db.scalars(payment_statement.order_by(models.BrandPayment.paid_on.desc()).limit(100)))

    billed_by_brand = defaultdict(float)
    actual_cost_by_brand = defaultdict(float)
    paid_by_brand = defaultdict(float)
    message_units_by_brand = defaultdict(int)
    input_tokens_by_brand = defaultdict(int)
    output_tokens_by_brand = defaultdict(int)

    for row in usage_rows:
        billed_by_brand[row.brand_id] += float(row.billed_amount_bdt or 0.0)
        actual_cost_by_brand[row.brand_id] += float(row.actual_cost_bdt or 0.0)
        message_units_by_brand[row.brand_id] += int(row.message_units or 0)
        input_tokens_by_brand[row.brand_id] += int(row.input_tokens or 0)
        output_tokens_by_brand[row.brand_id] += int(row.output_tokens or 0)

    all_payments = list(db.scalars(payment_statement))
    for payment in all_payments:
        paid_by_brand[payment.brand_id] += float(payment.amount_bdt or 0.0)

    brand_summaries = [
        CashFlowBrandSummaryOut(
            brand_id=brand.id,
            brand_name=brand.name,
            billed_amount_bdt=round(billed_by_brand.get(brand.id, 0.0), 6),
            actual_cost_bdt=round(actual_cost_by_brand.get(brand.id, 0.0), 6),
            paid_amount_bdt=round(paid_by_brand.get(brand.id, 0.0), 6),
            due_amount_bdt=round(billed_by_brand.get(brand.id, 0.0) - paid_by_brand.get(brand.id, 0.0), 6),
            profit_bdt=round(billed_by_brand.get(brand.id, 0.0) - actual_cost_by_brand.get(brand.id, 0.0), 6),
            message_units=message_units_by_brand.get(brand.id, 0),
            input_tokens=input_tokens_by_brand.get(brand.id, 0),
            output_tokens=output_tokens_by_brand.get(brand.id, 0),
        )
        for brand in brands
    ]

    totals = CashFlowTotalsOut(
        billed_amount_bdt=round(sum(item.billed_amount_bdt for item in brand_summaries), 6),
        actual_cost_bdt=round(sum(item.actual_cost_bdt for item in brand_summaries), 6),
        paid_amount_bdt=round(sum(item.paid_amount_bdt for item in brand_summaries), 6),
        due_amount_bdt=round(sum(item.due_amount_bdt for item in brand_summaries), 6),
        profit_bdt=round(sum(item.profit_bdt for item in brand_summaries), 6),
        message_units=sum(item.message_units for item in brand_summaries),
        input_tokens=sum(item.input_tokens for item in brand_summaries),
        output_tokens=sum(item.output_tokens for item in brand_summaries),
    )

    return CashFlowOverviewOut(
        period=period,
        start_at=start_at.isoformat(),
        end_at=end_at.isoformat(),
        totals=totals,
        brands=brand_summaries,
        payments=[CashFlowPaymentOut.model_validate(payment) for payment in payment_rows],
    )


@router.get("/payments", response_model=list[CashFlowPaymentOut])
def list_cash_flow_payments(db: DbSession, brand_id: int | None = None) -> list[CashFlowPaymentOut]:
    statement = select(models.BrandPayment).order_by(models.BrandPayment.paid_on.desc(), models.BrandPayment.created_at.desc())
    if brand_id is not None:
        statement = statement.where(models.BrandPayment.brand_id == brand_id)
    return [CashFlowPaymentOut.model_validate(item) for item in db.scalars(statement)]


@router.post("/payments", response_model=CashFlowPaymentOut)
def create_cash_flow_payment(payload: CashFlowPaymentCreate, db: DbSession) -> CashFlowPaymentOut:
    row = models.BrandPayment(
        brand_id=payload.brand_id,
        amount_bdt=payload.amount_bdt,
        paid_on=payload.paid_on,
        notes=payload.notes,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return CashFlowPaymentOut.model_validate(row)

