from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from app.api.schemas.brands import BrandOut
from app.api.schemas.jobs import JobOut


class BrandOptionOut(BaseModel):
    id: int
    name: str
    slug: str
    active: bool


class BrandDashboardStatsOut(BaseModel):
    rules: int = 0
    style_examples: int = 0
    knowledge_documents: int = 0
    customers: int = 0
    conversations: int = 0
    handoffs: int = 0
    uploads: int = 0
    product_images: int = 0


class BrandDashboardSummaryOut(BrandOut):
    model_config = ConfigDict(from_attributes=True)

    stats: BrandDashboardStatsOut


class DashboardHealthOut(BaseModel):
    status: str
    app: str
    env: str
    llm_provider: str
    speech_provider: str


class DashboardTotalsOut(BaseModel):
    brands: int
    conversations: int
    handoffs: int
    pending_jobs: int
    failed_jobs: int
    feedback_items: int


class DashboardChartPointOut(BaseModel):
    date: str
    conversations: int
    jobs: int


class DashboardOverviewOut(BaseModel):
    totals: DashboardTotalsOut
    health: DashboardHealthOut
    recent_jobs: list[JobOut]
    chart: list[DashboardChartPointOut]
    brand_options: list[BrandOptionOut]
