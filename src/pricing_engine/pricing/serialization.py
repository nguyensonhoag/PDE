"""JSON-safe serialization for PriceDecision — shared by the API response and
(indirectly) the persistence layer, so there's one source of truth for how a
Decimal/datetime-bearing decision becomes plain dict/str data.
"""

from __future__ import annotations

from pricing_engine.pricing.models import PriceDecision


def decision_to_dict(decision: PriceDecision) -> dict[str, object]:
    return {
        "product_id": decision.product_id,
        "base_price": str(decision.base_price),
        "final_price": str(decision.final_price),
        "rule_adjustments": [
            {
                "rule_name": a.rule_name,
                "adjustment_type": a.adjustment_type,
                "value": str(a.value),
                "reason": a.reason,
                "fired": a.fired,
            }
            for a in decision.rule_adjustments
        ],
        "guardrail_results": [
            {
                "guardrail_name": g.guardrail_name,
                "passed": g.passed,
                "original_price": str(g.original_price),
                "adjusted_price": str(g.adjusted_price),
                "reason": g.reason,
            }
            for g in decision.guardrail_results
        ],
        "decided_at": decision.decided_at.isoformat(),
        "variant": decision.variant,
    }
