"""Shared data structures for pricing rules, guardrails, and the engine.

PriceDecision is the audit-trail record: every rule's contribution (fired or not)
and every guardrail's outcome is captured alongside the final price.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Any


@dataclass(frozen=True)
class PricingContext:
    """All inputs available to rules/guardrails for one pricing decision."""

    product_id: str
    base_price: Decimal
    cost: Decimal
    inventory_level: int
    inventory_threshold_low: int = 10
    competitor_prices: tuple[Decimal, ...] = ()
    current_time: datetime = field(default_factory=datetime.utcnow)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class RuleAdjustment:
    """One rule's contribution to the price, always attached to a reason for the audit trail."""

    rule_name: str
    adjustment_type: str  # "multiplicative" | "additive"
    value: Decimal
    reason: str
    fired: bool = True


@dataclass(frozen=True)
class GuardrailResult:
    """Outcome of one guardrail check against a candidate price."""

    guardrail_name: str
    passed: bool
    original_price: Decimal
    adjusted_price: Decimal
    reason: str


@dataclass(frozen=True)
class PriceDecision:
    """Full audit-trail record for one pricing decision — the engine's sole output.

    variant is an experimentation-layer label (Phase 5), not something the
    engine or any rule/guardrail computes — it defaults to "control" here and
    is only ever overridden by the route after decide_price() returns.
    """

    product_id: str
    base_price: Decimal
    final_price: Decimal
    rule_adjustments: tuple[RuleAdjustment, ...]
    guardrail_results: tuple[GuardrailResult, ...]
    decided_at: datetime
    context_snapshot: PricingContext
    variant: str = "control"
