from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import case, func, select

from app import models
from app.api.deps import DbSession, require_platform_access
from app.api.routes.health import healthcheck
from app.api.schemas.brands import serialize_brand_output
from app.api.schemas.dashboard import (
    DashboardBrandFinancialOut,
    BrandDashboardStatsOut,
    BrandDashboardSummaryOut,
    BrandOptionOut,
    DashboardChartPointOut,
    DashboardHealthOut,
    DashboardOverviewOut,
    DashboardPeriodOut,
    DashboardTotalsOut,
    DashboardUsageBreakdownOut,
)
from app.api.schemas.jobs import JobOut
from app.services.brand_service import GLOBAL_BRAND_SLUG
from app.services.billing import resolve_period_bounds

router = APIRouter(prefix="/v1/dashboard", dependencies=[Depends(require_platform_access)])


def _ensure_utc_datetime(value: datetime | None) -> datetime | None:
    if not isinstance(value, datetime):
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _group_counts(db: DbSession, column) -> dict[int, int]:
    rows = db.execute(select(column, func.count()).group_by(column)).all()
    return {int(key): int(count) for key, count in rows}


def _conversation_counts(db: DbSession) -> dict[int, dict[str, int]]:
    rows = db.execute(
        select(
            models.Conversation.brand_id,
            func.count().label("conversation_count"),
            func.sum(case((models.Conversation.status == "handoff", 1), else_=0)).label("handoff_count"),
        ).group_by(models.Conversation.brand_id)
    ).all()
    return {
        int(brand_id): {
            "conversations": int(conversation_count or 0),
            "handoffs": int(handoff_count or 0),
        }
        for brand_id, conversation_count, handoff_count in rows
    }


def _brand_options(brands: list[models.Brand]) -> list[BrandOptionOut]:
    return [
        BrandOptionOut(
            id=brand.id,
            name=brand.name,
            slug=brand.slug,
            active=brand.active,
        )
        for brand in brands
    ]


@router.get("/brands", response_model=list[BrandDashboardSummaryOut])
def list_dashboard_brands(db: DbSession) -> list[BrandDashboardSummaryOut]:
    brands = list(
        db.scalars(
            select(models.Brand)
            .where(models.Brand.slug != GLOBAL_BRAND_SLUG)
            .order_by(models.Brand.created_at.desc())
        )
    )
    rules = _group_counts(db, models.BrandRule.brand_id)
    examples = _group_counts(db, models.StyleExample.brand_id)
    documents = _group_counts(db, models.KnowledgeDocument.brand_id)
    customers = _group_counts(db, models.Customer.brand_id)
    uploads = _group_counts(db, models.Attachment.brand_id)
    products = _group_counts(db, models.ProductImage.brand_id)
    conversation_counts = _conversation_counts(db)

    summaries: list[BrandDashboardSummaryOut] = []
    for brand in brands:
        brand_data = serialize_brand_output(brand, include_llm_secret=True).model_dump()
        stats = BrandDashboardStatsOut(
            rules=rules.get(brand.id, 0),
            style_examples=examples.get(brand.id, 0),
            knowledge_documents=documents.get(brand.id, 0),
            customers=customers.get(brand.id, 0),
            conversations=conversation_counts.get(brand.id, {}).get("conversations", 0),
            handoffs=conversation_counts.get(brand.id, {}).get("handoffs", 0),
            uploads=uploads.get(brand.id, 0),
            product_images=products.get(brand.id, 0),
        )
        summaries.append(BrandDashboardSummaryOut(**brand_data, stats=stats))

    return summaries


@router.get("/overview", response_model=DashboardOverviewOut)
def get_dashboard_overview(
    db: DbSession,
    brand_id: int | None = None,
    period: str = "today",
    custom_date: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
) -> DashboardOverviewOut:
    start_at, end_at = resolve_period_bounds(
        period,
        custom_date=custom_date,
        start_date=start_date,
        end_date=end_date,
    )

    brand_statement = (
        select(models.Brand)
        .where(models.Brand.slug != GLOBAL_BRAND_SLUG)
        .order_by(models.Brand.created_at.desc())
    )
    if brand_id is not None:
        brand_statement = brand_statement.where(models.Brand.id == brand_id)

    brands = list(db.scalars(brand_statement))
    brand_ids = [brand.id for brand in brands]
    recent_jobs_statement = select(models.Job).order_by(models.Job.created_at.desc()).limit(8)
    if brand_ids:
        recent_jobs_statement = recent_jobs_statement.where(models.Job.brand_id.in_(brand_ids))
    recent_jobs = list(db.scalars(recent_jobs_statement))

    conversation_statement = select(models.Conversation)
    if brand_ids:
        conversation_statement = conversation_statement.where(models.Conversation.brand_id.in_(brand_ids))
    conversations = list(db.scalars(conversation_statement))

    job_totals_statement = select(
        func.sum(case((models.Job.status == "pending", 1), else_=0)),
        func.sum(case((models.Job.status == "failed", 1), else_=0)),
    )
    if brand_ids:
        job_totals_statement = job_totals_statement.where(models.Job.brand_id.in_(brand_ids))
    job_totals = db.execute(job_totals_statement).one()

    feedback_statement = select(func.count(models.FeedbackEvent.id))
    if brand_ids:
        feedback_statement = feedback_statement.where(models.FeedbackEvent.brand_id.in_(brand_ids))
    feedback_count = int(db.scalar(feedback_statement) or 0)

    customer_statement = select(func.count(models.Customer.id))
    if brand_ids:
        customer_statement = customer_statement.where(models.Customer.brand_id.in_(brand_ids))
    customer_count = int(db.scalar(customer_statement) or 0)

    usage_all_statement = select(models.UsageRecord)
    usage_period_statement = select(models.UsageRecord).where(
        models.UsageRecord.occurred_at >= start_at,
        models.UsageRecord.occurred_at < end_at,
    )
    payment_statement = select(models.BrandPayment)
    if brand_ids:
        usage_all_statement = usage_all_statement.where(models.UsageRecord.brand_id.in_(brand_ids))
        usage_period_statement = usage_period_statement.where(models.UsageRecord.brand_id.in_(brand_ids))
        payment_statement = payment_statement.where(models.BrandPayment.brand_id.in_(brand_ids))

    usage_all = list(db.scalars(usage_all_statement))
    usage_period = list(db.scalars(usage_period_statement))
    payments = list(db.scalars(payment_statement))

    brand_lookup = {brand.id: brand for brand in brands}
    payments_by_brand = defaultdict(float)
    for payment in payments:
        payments_by_brand[payment.brand_id] += float(payment.amount_bdt or 0.0)

    all_billed_by_brand = defaultdict(float)
    period_billed_by_brand = defaultdict(float)
    period_cost_by_brand = defaultdict(float)
    period_units_by_brand = defaultdict(int)
    period_input_by_brand = defaultdict(int)
    period_output_by_brand = defaultdict(int)
    usage_breakdown_rows = defaultdict(lambda: {"message_units": 0, "input_tokens": 0, "output_tokens": 0, "billed_amount_bdt": 0.0, "actual_cost_bdt": 0.0})
    timeline: dict[str, dict[str, float]] = defaultdict(
        lambda: {"conversations": 0, "jobs": 0, "ai_messages": 0, "billed_amount_bdt": 0.0, "actual_cost_bdt": 0.0}
    )

    for row in usage_all:
        all_billed_by_brand[row.brand_id] += float(row.billed_amount_bdt or 0.0)

    for row in usage_period:
        period_billed_by_brand[row.brand_id] += float(row.billed_amount_bdt or 0.0)
        period_cost_by_brand[row.brand_id] += float(row.actual_cost_bdt or 0.0)
        period_units_by_brand[row.brand_id] += int(row.message_units or 0)
        period_input_by_brand[row.brand_id] += int(row.input_tokens or 0)
        period_output_by_brand[row.brand_id] += int(row.output_tokens or 0)

        usage_bucket = usage_breakdown_rows[row.usage_type]
        usage_bucket["message_units"] += int(row.message_units or 0)
        usage_bucket["input_tokens"] += int(row.input_tokens or 0)
        usage_bucket["output_tokens"] += int(row.output_tokens or 0)
        usage_bucket["billed_amount_bdt"] += float(row.billed_amount_bdt or 0.0)
        usage_bucket["actual_cost_bdt"] += float(row.actual_cost_bdt or 0.0)

        when = _ensure_utc_datetime(row.occurred_at)
        if when is not None:
            day = when.date().isoformat()
            timeline[day]["ai_messages"] += int(row.message_units or 0)
            timeline[day]["billed_amount_bdt"] += float(row.billed_amount_bdt or 0.0)
            timeline[day]["actual_cost_bdt"] += float(row.actual_cost_bdt or 0.0)

    handoffs = 0
    period_conversations = 0
    for conversation in conversations:
        if conversation.status == "handoff":
            handoffs += 1
        when = _ensure_utc_datetime(conversation.last_message_at or conversation.updated_at or conversation.created_at)
        if when is None:
            continue
        if start_at <= when < end_at:
            day = when.date().isoformat()
            timeline[day]["conversations"] += 1
            period_conversations += 1

    job_rows_statement = select(models.Job.created_at)
    if brand_ids:
        job_rows_statement = job_rows_statement.where(models.Job.brand_id.in_(brand_ids))
    for (created_at_value,) in db.execute(job_rows_statement).all():
        normalized_created_at = _ensure_utc_datetime(created_at_value)
        if normalized_created_at is None:
            continue
        if start_at <= normalized_created_at < end_at:
            timeline[normalized_created_at.date().isoformat()]["jobs"] += 1

    chart = [
        DashboardChartPointOut(
            date=day,
            conversations=int(values["conversations"]),
            jobs=int(values["jobs"]),
            ai_messages=int(values["ai_messages"]),
            billed_amount_bdt=round(float(values["billed_amount_bdt"]), 6),
            actual_cost_bdt=round(float(values["actual_cost_bdt"]), 6),
        )
        for day, values in sorted(timeline.items())
    ]

    brand_financials = [
        DashboardBrandFinancialOut(
            brand_id=brand.id,
            brand_name=brand.name,
            message_units=period_units_by_brand.get(brand.id, 0),
            input_tokens=period_input_by_brand.get(brand.id, 0),
            output_tokens=period_output_by_brand.get(brand.id, 0),
            due_amount_bdt=round(all_billed_by_brand.get(brand.id, 0.0) - payments_by_brand.get(brand.id, 0.0), 6),
            actual_cost_bdt=round(period_cost_by_brand.get(brand.id, 0.0), 6),
            paid_amount_bdt=round(payments_by_brand.get(brand.id, 0.0), 6),
            profit_bdt=round(period_billed_by_brand.get(brand.id, 0.0) - period_cost_by_brand.get(brand.id, 0.0), 6),
        )
        for brand in brands
    ]

    usage_breakdown = [
        DashboardUsageBreakdownOut(
            usage_type=usage_type,
            message_units=int(values["message_units"]),
            input_tokens=int(values["input_tokens"]),
            output_tokens=int(values["output_tokens"]),
            billed_amount_bdt=round(float(values["billed_amount_bdt"]), 6),
            actual_cost_bdt=round(float(values["actual_cost_bdt"]), 6),
        )
        for usage_type, values in sorted(usage_breakdown_rows.items())
    ]

    outstanding_due = sum(item.due_amount_bdt for item in brand_financials)
    period_actual_cost = sum(item.actual_cost_bdt for item in brand_financials)
    period_profit = sum(item.profit_bdt for item in brand_financials)
    total_ai_messages = sum(item.message_units for item in brand_financials)

    health = DashboardHealthOut(**healthcheck())

    return DashboardOverviewOut(
        totals=DashboardTotalsOut(
            brands=len(brands),
            conversations=period_conversations,
            handoffs=handoffs,
            pending_jobs=int(job_totals[0] or 0),
            failed_jobs=int(job_totals[1] or 0),
            feedback_items=feedback_count,
            customers=customer_count,
            ai_messages=total_ai_messages,
            due_amount_bdt=round(outstanding_due, 6),
            actual_cost_bdt=round(period_actual_cost, 6),
            profit_bdt=round(period_profit, 6),
        ),
        health=health,
        recent_jobs=[JobOut.model_validate(job) for job in recent_jobs],
        chart=chart,
        brand_options=_brand_options(brands),
        period=DashboardPeriodOut(
            period=period,
            start_at=start_at.isoformat(),
            end_at=end_at.isoformat(),
        ),
        usage_breakdown=usage_breakdown,
        brand_financials=brand_financials,
    )
