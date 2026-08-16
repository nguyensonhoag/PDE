"""Pricing rules: each rule independently evaluates a PricingContext and proposes a
relative adjustment (multiplicative factor) to the running price. Rules never compute
absolute prices themselves — the engine owns all price arithmetic so every step is
auditable in one place. A rule that doesn't apply returns fired=False with a neutral
(1.0) multiplicative value rather than raising.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from decimal import Decimal

from .models import PricingContext, RuleAdjustment

NEUTRAL = Decimal(1)


class PricingRule(ABC):
    """Base interface all pricing rules implement."""

    name: str

    @abstractmethod
    def evaluate(self, context: PricingContext) -> RuleAdjustment:
        """Return this rule's effect on the price for the given context."""
        raise NotImplementedError


class InventoryBasedRule(PricingRule):
    """Raise price when inventory is scarce, lower it when overstocked."""

    name = "inventory_based"

    def __init__(
        self,
        low_stock_multiplier: Decimal = Decimal("1.15"),
        overstock_multiplier: Decimal = Decimal("0.90"),
        overstock_threshold: int = 200,
    ) -> None:
        self._low_stock_multiplier = low_stock_multiplier
        self._overstock_multiplier = overstock_multiplier
        self._overstock_threshold = overstock_threshold

    def evaluate(self, context: PricingContext) -> RuleAdjustment:
        if context.inventory_level <= context.inventory_threshold_low:
            return RuleAdjustment(
                rule_name=self.name,
                adjustment_type="multiplicative",
                value=self._low_stock_multiplier,
                reason=(
                    f"inventory_level={context.inventory_level} at or below low threshold "
                    f"={context.inventory_threshold_low}; applying scarcity multiplier"
                ),
                fired=True,
            )
        if context.inventory_level >= self._overstock_threshold:
            return RuleAdjustment(
                rule_name=self.name,
                adjustment_type="multiplicative",
                value=self._overstock_multiplier,
                reason=(
                    f"inventory_level={context.inventory_level} at or above overstock "
                    f"threshold={self._overstock_threshold}; applying overstock discount"
                ),
                fired=True,
            )
        return RuleAdjustment(
            rule_name=self.name,
            adjustment_type="multiplicative",
            value=NEUTRAL,
            reason=f"inventory_level={context.inventory_level} within normal range; no adjustment",
            fired=False,
        )


class TimeBasedRule(PricingRule):
    """Apply a peak-hour surcharge based on context.current_time. Peak window is
    [peak_hours[0], peak_hours[1]) — start inclusive, end exclusive."""

    name = "time_based"

    def __init__(
        self,
        peak_hours: tuple[int, int] = (17, 21),
        peak_multiplier: Decimal = Decimal("1.10"),
        off_peak_multiplier: Decimal = Decimal("1.00"),
    ) -> None:
        self._peak_start, self._peak_end = peak_hours
        self._peak_multiplier = peak_multiplier
        self._off_peak_multiplier = off_peak_multiplier

    def evaluate(self, context: PricingContext) -> RuleAdjustment:
        hour = context.current_time.hour
        if self._peak_start <= hour < self._peak_end:
            return RuleAdjustment(
                rule_name=self.name,
                adjustment_type="multiplicative",
                value=self._peak_multiplier,
                reason=(
                    f"hour={hour} within peak window [{self._peak_start}, {self._peak_end}); "
                    "applying peak surcharge"
                ),
                fired=True,
            )
        return RuleAdjustment(
            rule_name=self.name,
            adjustment_type="multiplicative",
            value=self._off_peak_multiplier,
            reason=(
                f"hour={hour} outside peak window [{self._peak_start}, {self._peak_end}); "
                "no surcharge"
            ),
            fired=False,
        )


class CompetitorBasedRule(PricingRule):
    """Position price relative to observed competitor prices.

    Adjustments are expressed as a multiplicative factor computed against
    context.base_price (e.g. "target / base_price"), since evaluate() only receives
    the context and not the engine's running price. If this rule runs after other
    multiplicative rules, the final price will diverge from a pure competitor match —
    that's expected and covered by the engine's rule-order tests.
    """

    name = "competitor_based"

    def __init__(
        self,
        strategy: str = "match_min",
        undercut_percent: Decimal = Decimal("0.02"),
    ) -> None:
        if strategy not in {"match_min", "undercut_percent", "match_avg"}:
            raise ValueError(f"unknown competitor strategy: {strategy!r}")
        self._strategy = strategy
        self._undercut_percent = undercut_percent

    def evaluate(self, context: PricingContext) -> RuleAdjustment:
        if not context.competitor_prices:
            return RuleAdjustment(
                rule_name=self.name,
                adjustment_type="multiplicative",
                value=NEUTRAL,
                reason="no competitor price data available; no adjustment",
                fired=False,
            )

        if self._strategy == "match_min":
            target = min(context.competitor_prices)
            reason = f"matching lowest competitor price {target}"
        elif self._strategy == "match_avg":
            target = sum(context.competitor_prices) / Decimal(len(context.competitor_prices))
            reason = f"matching average competitor price {target}"
        else:  # undercut_percent
            lowest = min(context.competitor_prices)
            target = lowest * (Decimal(1) - self._undercut_percent)
            reason = (
                f"undercutting lowest competitor price {lowest} by "
                f"{self._undercut_percent:%}: target {target}"
            )

        value = target / context.base_price
        return RuleAdjustment(
            rule_name=self.name,
            adjustment_type="multiplicative",
            value=value,
            reason=reason,
            fired=True,
        )
