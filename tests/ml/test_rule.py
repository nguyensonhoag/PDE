from __future__ import annotations

from decimal import Decimal

from pricing_engine.ml.rule import DemandElasticityRule
from pricing_engine.pricing.engine import PricingEngine
from pricing_engine.pricing.guardrails import MarginFloorGuardrail, MinMaxGuardrail


class StubDemandModel:
    def __init__(self, elasticity: float | None) -> None:
        self._elasticity = elasticity

    def predict_elasticity(self, route, days_to_departure, seats_remaining_before, price):
        return self._elasticity


class TestDemandElasticityRule:
    def test_no_ops_when_model_file_missing(self, make_context):
        rule = DemandElasticityRule(model_path="/nonexistent/model.joblib")
        context = make_context(metadata={"route": "JFK-LAX", "days_to_departure": 10})

        adjustment = rule.evaluate(context)

        assert adjustment.fired is False
        assert adjustment.value == Decimal(1)

    def test_no_ops_when_metadata_missing_route_or_days_to_departure(self, make_context):
        rule = DemandElasticityRule(model=StubDemandModel(elasticity=-2.0))
        context = make_context(metadata={})

        adjustment = rule.evaluate(context)

        assert adjustment.fired is False

    def test_no_ops_when_elasticity_is_unavailable(self, make_context):
        rule = DemandElasticityRule(model=StubDemandModel(elasticity=None))
        context = make_context(metadata={"route": "JFK-LAX", "days_to_departure": 10})

        adjustment = rule.evaluate(context)

        assert adjustment.fired is False

    def test_applies_floor_adjustment_for_elastic_demand(self, make_context):
        rule = DemandElasticityRule(model=StubDemandModel(elasticity=-3.0))
        context = make_context(metadata={"route": "JFK-LAX", "days_to_departure": 10})

        adjustment = rule.evaluate(context)

        assert adjustment.fired is True
        assert adjustment.value == Decimal("0.85")

    def test_applies_neutral_adjustment_for_unit_elasticity(self, make_context):
        rule = DemandElasticityRule(model=StubDemandModel(elasticity=-1.0))
        context = make_context(metadata={"route": "JFK-LAX", "days_to_departure": 10})

        adjustment = rule.evaluate(context)

        assert adjustment.value == Decimal("1.00")

    def test_applies_ceiling_adjustment_for_inelastic_demand(self, make_context):
        rule = DemandElasticityRule(model=StubDemandModel(elasticity=-0.3))
        context = make_context(metadata={"route": "JFK-LAX", "days_to_departure": 10})

        adjustment = rule.evaluate(context)

        assert adjustment.value == Decimal("1.15")

    def test_adjustment_is_bounded_for_extreme_elasticity(self, make_context):
        rule = DemandElasticityRule(model=StubDemandModel(elasticity=-100.0))
        context = make_context(metadata={"route": "JFK-LAX", "days_to_departure": 10})

        adjustment = rule.evaluate(context)

        assert adjustment.value == Decimal("0.85")

    def test_composes_with_guardrails_via_full_engine(self, make_context):
        rule = DemandElasticityRule(model=StubDemandModel(elasticity=-0.3))
        engine = PricingEngine(
            rules=[rule],
            guardrails=[
                MinMaxGuardrail(min_price=Decimal("10.00"), max_price=Decimal("500.00")),
                MarginFloorGuardrail(min_margin_pct=Decimal("0.10")),
            ],
        )
        context = make_context(
            base_price=Decimal("490.00"),
            cost=Decimal("400.00"),
            metadata={"route": "JFK-LAX", "days_to_departure": 10},
        )

        decision = engine.decide_price(context)

        # 490.00 * 1.15 = 563.50, clamped down to the 500.00 max
        assert decision.final_price == Decimal("500.00")
