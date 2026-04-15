from __future__ import annotations

from dataclasses import dataclass, field

from app import models


RISK_KEYWORDS = {
    "refund": "Refund request needs human review.",
    "chargeback": "Billing conflict should go to a human.",
    "lawsuit": "Legal threat should go to a human.",
    "lawyer": "Legal threat should go to a human.",
    "angry": "Escalated tone detected.",
    "fraud": "Sensitive fraud concern detected.",
    "discount": "Discount negotiation can need human approval.",
    "custom price": "Custom pricing can need human approval.",
    "manager": "Customer asked for a manager.",
}


@dataclass
class ModerationDecision:
    force_handoff: bool = False
    reason: str | None = None
    flags: list[str] = field(default_factory=list)


def inspect_customer_message(text: str, brand_rules: list[models.BrandRule]) -> ModerationDecision:
    lower = text.lower()
    flags: list[str] = []
    reason: str | None = None
    force_handoff = False

    for keyword, message in RISK_KEYWORDS.items():
        if keyword in lower:
            flags.append(f"risk:{keyword}")
            if not reason:
                reason = message
            if keyword in {"refund", "chargeback", "lawsuit", "lawyer", "fraud", "manager"}:
                force_handoff = True

    for rule in brand_rules:
        if rule.handoff_on_match and rule.title.lower() in lower:
            flags.append(f"brand-rule:{rule.title.lower()}")
            force_handoff = True
            reason = reason or f"Matched handoff rule: {rule.title}"

    return ModerationDecision(force_handoff=force_handoff, reason=reason, flags=flags)
