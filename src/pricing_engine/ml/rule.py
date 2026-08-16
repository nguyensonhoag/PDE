"""Plugs the trained demand model into the pricing engine as one more rule —
no engine/ABC changes needed, that seam was already designed for this. Reads
its inputs (route, days_to_departure) from context.metadata, which the
existing generic PricingContext already supports as an extension point.
"""

from __future__ import annotations

import os
from decimal import Decimal

from pricing_engine.config import DEMAND_MODEL_PATH
from pricing_engine.ml.model import DemandModel
from pricing_engine.pricing.models import PricingContext, RuleAdjustment
from pricing_engine.pricing.rules import PricingRule

NEUTRAL = Decimal(1)

_ELASTIC_THRESHOLD = Decimal("-3.0")
_UNIT_THRESHOLD = Decimal("-1.0")
_INELASTIC_THRESHOLD = Decimal("-0.3")
_MULTIPLIER_FLOOR = Decimal("0.85")
_MULTIPLIER_NEUTRAL = Decimal("1.00")
_MULTIPLIER_CEILING = Decimal("1.15")


def _elasticity_to_multiplier(elasticity: float) -> Decimal:
    """Bounded, piecewise-linear map from predicted elasticity to a price
    multiplier: highly elastic demand (<= -3.0) gets a 15% discount to
    encourage bookings; highly inelastic demand (>= -0.3) gets a 15%
    surcharge to capture willingness to pay; unit elasticity (-1.0) is
    neutral. Always clamped to [0.85, 1.15] regardless of how extreme the
    input is.
    """
    e = Decimal(str(elasticity))
    if e <= _ELASTIC_THRESHOLD:
        return _MULTIPLIER_FLOOR
    if e >= _INELASTIC_THRESHOLD:
        return _MULTIPLIER_CEILING
    if e <= _UNIT_THRESHOLD:
        t = (e - _ELASTIC_THRESHOLD) / (_UNIT_THRESHOLD - _ELASTIC_THRESHOLD)
        return _MULTIPLIER_FLOOR + t * (_MULTIPLIER_NEUTRAL - _MULTIPLIER_FLOOR)
    t = (e - _UNIT_THRESHOLD) / (_INELASTIC_THRESHOLD - _UNIT_THRESHOLD)
    return _MULTIPLIER_NEUTRAL + t * (_MULTIPLIER_CEILING - _MULTIPLIER_NEUTRAL)


class DemandElasticityRule(PricingRule):
    """No-ops (fired=False) for generic products (no route/days_to_departure
    in metadata) and when no trained model is available yet — same "doesn't
    apply -> fired=False, never raise" convention as the other rules.
    """

    name = "demand_elasticity"

    def __init__(self, model: DemandModel | None = None, model_path: str = DEMAND_MODEL_PATH) -> None:
        self._model = model
        self._model_path = model_path
        self._attempted_load = model is not None

    def _get_model(self) -> DemandModel | None:
        if not self._attempted_load:
            self._attempted_load = True
            if os.path.exists(self._model_path):
                self._model = DemandModel.load(self._model_path)
        return self._model

    def evaluate(self, context: PricingContext) -> RuleAdjustment:
        route = context.metadata.get("route")
        days_to_departure = context.metadata.get("days_to_departure")
        if route is None or days_to_departure is None:
            return self._no_op(
                "context.metadata missing route/days_to_departure; not a flight product"
            )

        model = self._get_model()
        if model is None:
            return self._no_op(f"no trained demand model found at {self._model_path!r}")

        elasticity = model.predict_elasticity(
            route=route,
            days_to_departure=days_to_departure,
            seats_remaining_before=context.inventory_level,
            price=float(context.base_price),
        )
        if elasticity is None:
            return self._no_op("predicted demand too low for a reliable elasticity estimate")

        multiplier = _elasticity_to_multiplier(elasticity)
        return RuleAdjustment(
            rule_name=self.name,
            adjustment_type="multiplicative",
            value=multiplier,
            reason=(
                f"predicted elasticity={elasticity:.2f} for route={route!r}, "
                f"days_to_departure={days_to_departure}"
            ),
            fired=True,
        )

    def _no_op(self, reason: str) -> RuleAdjustment:
        return RuleAdjustment(
            rule_name=self.name,
            adjustment_type="multiplicative",
            value=NEUTRAL,
            reason=reason,
            fired=False,
        )
