from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import models

MAIN_SYSTEM_PROMPT_KEY = "main_system_prompt"

DEFAULT_MAIN_SYSTEM_PROMPT = (
    "You are the main AI operating layer for a Bangladesh-focused sales and customer support system. "
    "Be accurate, concise, practical, and helpful. Never invent business facts, stock status, pricing, or policies. "
    "Prefer grounded answers from the brand knowledge base, approved conversation examples, customer history, "
    "recognized product details, and ad-specific knowledge when available. "
    "When the customer asks about a product, use the saved product description, stock status, sale price, and other "
    "brand-specific knowledge if relevant. If the message is risky, unclear, approval-sensitive, legal, abusive, "
    "or needs a human decision, choose handoff. If one short follow-up question is enough, choose clarify. "
    "Reply in natural Bangla used in Bangladesh unless the customer clearly prefers English."
)


def get_setting_record(db: Session, setting_key: str) -> models.AppSetting | None:
    return db.scalar(select(models.AppSetting).where(models.AppSetting.setting_key == setting_key))


def get_setting_value(db: Session, setting_key: str, default: dict[str, Any] | None = None) -> dict[str, Any]:
    row = get_setting_record(db, setting_key)
    if row and isinstance(row.value_json, dict):
        return dict(row.value_json)
    return dict(default or {})


def upsert_setting_value(db: Session, setting_key: str, value: dict[str, Any]) -> models.AppSetting:
    row = get_setting_record(db, setting_key)
    if row is None:
        row = models.AppSetting(setting_key=setting_key, value_json=value)
    else:
        row.value_json = value
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def get_main_system_prompt(db: Session) -> str:
    payload = get_setting_value(db, MAIN_SYSTEM_PROMPT_KEY, {"text": DEFAULT_MAIN_SYSTEM_PROMPT})
    text = str(payload.get("text") or "").strip()
    return text or DEFAULT_MAIN_SYSTEM_PROMPT

