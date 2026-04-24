from __future__ import annotations

from collections.abc import Iterable
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy.orm import Session

from app import models
from app.services.llm.runtime import extract_brand_billing_settings


def extract_token_counts(token_usage: dict | None) -> tuple[int, int]:
    usage = token_usage or {}
    prompt_tokens = _first_int(
        usage.get("prompt_tokens"),
        usage.get("prompt_token_count"),
        usage.get("input_tokens"),
        usage.get("input_token_count"),
    )
    completion_tokens = _first_int(
        usage.get("completion_tokens"),
        usage.get("candidates_token_count"),
        usage.get("output_tokens"),
        usage.get("output_token_count"),
    )
    return prompt_tokens, completion_tokens


def calculate_actual_cost_bdt(
    brand: models.Brand,
    usage_type: str,
    *,
    input_tokens: int,
    output_tokens: int,
) -> float:
    billing = extract_brand_billing_settings(brand)
    usage_key = usage_type if usage_type in {"text", "image", "audio"} else "text"
    usage_rates = billing.get(usage_key) if isinstance(billing.get(usage_key), dict) else {}
    input_rate = float((usage_rates or {}).get("input_cost_per_million_bdt") or 0.0)
    output_rate = float((usage_rates or {}).get("output_cost_per_million_bdt") or 0.0)
    return round(((input_tokens / 1_000_000) * input_rate) + ((output_tokens / 1_000_000) * output_rate), 6)


def calculate_billed_amount_bdt(brand: models.Brand, *, message_units: int) -> float:
    billing = extract_brand_billing_settings(brand)
    text_rates = billing.get("text") if isinstance(billing.get("text"), dict) else {}
    per_message_cost = float((text_rates or {}).get("per_message_cost_bdt") or 0.0)
    return round(per_message_cost * max(0, int(message_units)), 6)


def record_usage(
    db: Session,
    *,
    brand: models.Brand,
    channel: str,
    usage_type: str,
    provider: str | None,
    model: str | None,
    token_usage: dict | None = None,
    message_units: int = 0,
    conversation_id: int | None = None,
    message_id: int | None = None,
    metadata: dict | None = None,
    occurred_at: datetime | None = None,
) -> models.UsageRecord:
    input_tokens, output_tokens = extract_token_counts(token_usage)
    row = models.UsageRecord(
        brand_id=brand.id,
        conversation_id=conversation_id,
        message_id=message_id,
        channel=channel,
        usage_type=usage_type,
        provider=provider,
        model=model,
        message_units=max(0, int(message_units)),
        input_tokens=max(0, int(input_tokens)),
        output_tokens=max(0, int(output_tokens)),
        billed_amount_bdt=calculate_billed_amount_bdt(brand, message_units=message_units) if usage_type == "text" else 0.0,
        actual_cost_bdt=calculate_actual_cost_bdt(
            brand,
            usage_type,
            input_tokens=max(0, int(input_tokens)),
            output_tokens=max(0, int(output_tokens)),
        ),
        metadata_json=metadata or {},
        occurred_at=occurred_at or datetime.now(timezone.utc),
    )
    db.add(row)
    db.flush()
    return row


def resolve_period_bounds(
    period: str,
    *,
    custom_date: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    timezone_name: str = "Asia/Dhaka",
) -> tuple[datetime, datetime]:
    try:
        tz = ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError:
        tz = timezone.utc
    today = datetime.now(tz).date()
    normalized = (period or "today").strip().lower()

    if normalized == "today":
        start_local = datetime.combine(today, time.min, tzinfo=tz)
        end_local = start_local + timedelta(days=1)
    elif normalized == "week":
        start_of_week = today - timedelta(days=today.weekday())
        start_local = datetime.combine(start_of_week, time.min, tzinfo=tz)
        end_local = start_local + timedelta(days=7)
    elif normalized == "month":
        start_of_month = today.replace(day=1)
        if start_of_month.month == 12:
            next_month = start_of_month.replace(year=start_of_month.year + 1, month=1)
        else:
            next_month = start_of_month.replace(month=start_of_month.month + 1)
        start_local = datetime.combine(start_of_month, time.min, tzinfo=tz)
        end_local = datetime.combine(next_month, time.min, tzinfo=tz)
    elif normalized == "year":
        start_of_year = today.replace(month=1, day=1)
        next_year = start_of_year.replace(year=start_of_year.year + 1)
        start_local = datetime.combine(start_of_year, time.min, tzinfo=tz)
        end_local = datetime.combine(next_year, time.min, tzinfo=tz)
    elif normalized == "custom_date":
        selected_date = _parse_date(custom_date) or today
        start_local = datetime.combine(selected_date, time.min, tzinfo=tz)
        end_local = start_local + timedelta(days=1)
    else:
        resolved_start = _parse_date(start_date) or today
        resolved_end = _parse_date(end_date) or resolved_start
        if resolved_end < resolved_start:
            resolved_end = resolved_start
        start_local = datetime.combine(resolved_start, time.min, tzinfo=tz)
        end_local = datetime.combine(resolved_end + timedelta(days=1), time.min, tzinfo=tz)

    return start_local.astimezone(timezone.utc), end_local.astimezone(timezone.utc)


def daterange(start_inclusive: date, end_inclusive: date) -> Iterable[date]:
    current = start_inclusive
    while current <= end_inclusive:
        yield current
        current += timedelta(days=1)


def _parse_date(value: str | None) -> date | None:
    cleaned = str(value or "").strip()
    if not cleaned:
        return None
    try:
        return date.fromisoformat(cleaned)
    except ValueError:
        return None


def _first_int(*values: object) -> int:
    for value in values:
        try:
            if value is None or value == "":
                continue
            return max(0, int(float(str(value))))
        except (TypeError, ValueError):
            continue
    return 0
