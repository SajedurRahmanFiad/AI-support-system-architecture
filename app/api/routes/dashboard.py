from __future__ import annotations

from collections import defaultdict
from datetime import datetime

from fastapi import APIRouter, Depends
from sqlalchemy import case, func, select

from app import models
from app.api.deps import DbSession, require_platform_access
from app.api.routes.health import healthcheck
from app.api.schemas.brands import serialize_brand_output
from app.api.schemas.dashboard import (
    BrandDashboardStatsOut,
    BrandDashboardSummaryOut,
    BrandOptionOut,
    DashboardChartPointOut,
    DashboardHealthOut,
    DashboardOverviewOut,
    DashboardTotalsOut,
)
from app.api.schemas.jobs import JobOut
from app.services.brand_service import GLOBAL_BRAND_SLUG

router = APIRouter(prefix="/v1/dashboard", dependencies=[Depends(require_platform_access)])


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
def get_dashboard_overview(db: DbSession) -> DashboardOverviewOut:
    brands = list(
        db.scalars(
            select(models.Brand)
            .where(models.Brand.slug != GLOBAL_BRAND_SLUG)
            .order_by(models.Brand.created_at.desc())
        )
    )
    recent_jobs = list(db.scalars(select(models.Job).order_by(models.Job.created_at.desc()).limit(8)))

    conversation_totals = db.execute(
        select(
            func.count(models.Conversation.id),
            func.sum(case((models.Conversation.status == "handoff", 1), else_=0)),
        )
    ).one()
    job_totals = db.execute(
        select(
            func.sum(case((models.Job.status == "pending", 1), else_=0)),
            func.sum(case((models.Job.status == "failed", 1), else_=0)),
        )
    ).one()
    feedback_count = int(db.scalar(select(func.count(models.FeedbackEvent.id))) or 0)

    timeline: dict[str, dict[str, int]] = defaultdict(lambda: {"conversations": 0, "jobs": 0})
    conversation_rows = db.execute(
        select(
            models.Conversation.last_message_at,
            models.Conversation.updated_at,
            models.Conversation.created_at,
        )
    ).all()
    for last_message_at, updated_at, created_at in conversation_rows:
        when = last_message_at or updated_at or created_at
        if not isinstance(when, datetime):
            continue
        day = when.date().isoformat()
        timeline[day]["conversations"] += 1

    job_rows = db.execute(select(models.Job.created_at)).all()
    for (created_at,) in job_rows:
        if not isinstance(created_at, datetime):
            continue
        day = created_at.date().isoformat()
        timeline[day]["jobs"] += 1

    chart = [
        DashboardChartPointOut(
            date=day,
            conversations=row["conversations"],
            jobs=row["jobs"],
        )
        for day, row in sorted(timeline.items())[-7:]
    ]

    health = DashboardHealthOut(**healthcheck())

    return DashboardOverviewOut(
        totals=DashboardTotalsOut(
            brands=len(brands),
            conversations=int(conversation_totals[0] or 0),
            handoffs=int(conversation_totals[1] or 0),
            pending_jobs=int(job_totals[0] or 0),
            failed_jobs=int(job_totals[1] or 0),
            feedback_items=feedback_count,
        ),
        health=health,
        recent_jobs=[JobOut.model_validate(job) for job in recent_jobs],
        chart=chart,
        brand_options=_brand_options(brands),
    )
