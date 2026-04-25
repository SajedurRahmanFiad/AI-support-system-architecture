from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class CashFlowPaymentCreate(BaseModel):
    brand_id: int
    amount_bdt: float
    paid_on: datetime
    notes: str | None = None


class CashFlowPaymentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    brand_id: int
    amount_bdt: float
    paid_on: datetime
    notes: str | None = None
    created_at: datetime


class CashFlowBrandSummaryOut(BaseModel):
    brand_id: int
    brand_name: str
    billed_amount_bdt: float = 0.0
    actual_cost_bdt: float = 0.0
    paid_amount_bdt: float = 0.0
    due_amount_bdt: float = 0.0
    profit_bdt: float = 0.0
    message_units: int = 0
    input_tokens: int = 0
    output_tokens: int = 0


class CashFlowTotalsOut(BaseModel):
    billed_amount_bdt: float = 0.0
    actual_cost_bdt: float = 0.0
    paid_amount_bdt: float = 0.0
    due_amount_bdt: float = 0.0
    profit_bdt: float = 0.0
    message_units: int = 0
    input_tokens: int = 0
    output_tokens: int = 0


class CashFlowOverviewOut(BaseModel):
    period: str
    start_at: str
    end_at: str
    totals: CashFlowTotalsOut
    brands: list[CashFlowBrandSummaryOut]
    payments: list[CashFlowPaymentOut]
