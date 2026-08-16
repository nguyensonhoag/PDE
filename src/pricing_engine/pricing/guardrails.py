"""Guardrails clamp a candidate price into a safe range — they never reject outright,
which guarantees the engine can never emit a price outside business bounds without
needing a fallback path. Clamping is still recorded as passed=False for the audit trail.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from decimal import Decimal

from .models import GuardrailResult, PricingContext


class Guardrail(ABC):
    name: str

    @abstractmethod
    def apply(self, candidate_price: Decimal, context: PricingContext) -> GuardrailResult:
        """Check/clamp candidate_price; adjusted_price == candidate_price if untouched."""
        raise NotImplementedError


class MinMaxGuardrail(Guardrail):
    """Clamp the final price to an absolute [min_price, max_price] band (inclusive)."""

    name = "min_max"

    def __init__(self, min_price: Decimal, max_price: Decimal) -> None:
        if min_price > max_price:
            raise ValueError("min_price must be <= max_price")
        self._min_price = min_price
        self._max_price = max_price

    def apply(self, candidate_price: Decimal, context: PricingContext) -> GuardrailResult:
        if candidate_price < self._min_price:
            return GuardrailResult(
                guardrail_name=self.name,
                passed=False,
                original_price=candidate_price,
                adjusted_price=self._min_price,
                reason=f"price {candidate_price} below min {self._min_price}; clamped up",
            )
        if candidate_price > self._max_price:
            return GuardrailResult(
                guardrail_name=self.name,
                passed=False,
                original_price=candidate_price,
                adjusted_price=self._max_price,
                reason=f"price {candidate_price} above max {self._max_price}; clamped down",
            )
        return GuardrailResult(
            guardrail_name=self.name,
            passed=True,
            original_price=candidate_price,
            adjusted_price=candidate_price,
            reason=f"price {candidate_price} within [{self._min_price}, {self._max_price}]",
        )


class MarginFloorGuardrail(Guardrail):
    """Ensure price >= cost * (1 + min_margin_pct); clamps up if violated.

    If context.cost <= 0, margin is undefined for this product — the guardrail passes
    through unchanged rather than dividing by/against a meaningless cost basis.
    """

    name = "margin_floor"

    def __init__(self, min_margin_pct: Decimal = Decimal("0.10")) -> None:
        self._min_margin_pct = min_margin_pct

    def apply(self, candidate_price: Decimal, context: PricingContext) -> GuardrailResult:
        if context.cost <= 0:
            return GuardrailResult(
                guardrail_name=self.name,
                passed=True,
                original_price=candidate_price,
                adjusted_price=candidate_price,
                reason=f"cost={context.cost} <= 0; margin floor undefined, no adjustment",
            )

        floor = context.cost * (Decimal(1) + self._min_margin_pct)
        if candidate_price < floor:
            return GuardrailResult(
                guardrail_name=self.name,
                passed=False,
                original_price=candidate_price,
                adjusted_price=floor,
                reason=(
                    f"price {candidate_price} below margin floor {floor} "
                    f"(cost={context.cost}, min_margin_pct={self._min_margin_pct}); clamped up"
                ),
            )
        return GuardrailResult(
            guardrail_name=self.name,
            passed=True,
            original_price=candidate_price,
            adjusted_price=candidate_price,
            reason=f"price {candidate_price} at or above margin floor {floor}",
        )
