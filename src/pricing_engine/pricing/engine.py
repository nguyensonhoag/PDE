"""Orchestrates rules -> guardrails -> final price into a single auditable PriceDecision.

Rule inapplicability is signaled via RuleAdjustment.fired=False, never an exception —
only malformed input should raise, and only before any rule runs, so the audit trail
is never left partially built.
"""

from __future__ import annotations

from datetime import datetime

from .guardrails import Guardrail
from .models import PriceDecision, PricingContext
from .rules import PricingRule


class PricingEngine:
    def __init__(self, rules: list[PricingRule], guardrails: list[Guardrail]) -> None:
        self._rules = rules
        self._guardrails = guardrails

    def decide_price(self, context: PricingContext) -> PriceDecision:
        if not isinstance(context, PricingContext):
            raise TypeError(f"expected PricingContext, got {type(context)!r}")

        price = context.base_price
        rule_adjustments = []
        for rule in self._rules:
            adjustment = rule.evaluate(context)
            rule_adjustments.append(adjustment)
            if adjustment.fired:
                if adjustment.adjustment_type == "multiplicative":
                    price *= adjustment.value
                elif adjustment.adjustment_type == "additive":
                    price += adjustment.value
                else:
                    raise ValueError(f"unknown adjustment_type: {adjustment.adjustment_type!r}")

        guardrail_results = []
        for guardrail in self._guardrails:
            result = guardrail.apply(price, context)
            guardrail_results.append(result)
            price = result.adjusted_price

        return PriceDecision(
            product_id=context.product_id,
            base_price=context.base_price,
            final_price=price,
            rule_adjustments=tuple(rule_adjustments),
            guardrail_results=tuple(guardrail_results),
            decided_at=datetime.utcnow(),
            context_snapshot=context,
        )
