from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pricing_engine.experimentation.metrics import summarize_by_variant
from pricing_engine.pricing.models import PriceDecision


class StubDemandModel:
    def predict_demand(self, route, days_to_departure, seats_remaining_before, price):
        return 5.0


def _decision(make_context, variant: str, final_price: Decimal, metadata=None) -> PriceDecision:
    context = make_context(metadata=metadata or {})
    return PriceDecision(
        product_id=context.product_id,
        base_price=context.base_price,
        final_price=final_price,
        rule_adjustments=(),
        guardrail_results=(),
        decided_at=datetime(2024, 1, 1),
        context_snapshot=context,
        variant=variant,
    )


class TestSummarizeByVariant:
    def test_computes_mean_final_price_per_variant(self, make_context):
        decisions = [
            _decision(make_context, "control", Decimal(100)),
            _decision(make_context, "control", Decimal(200)),
            _decision(make_context, "treatment", Decimal(90)),
        ]

        summaries = summarize_by_variant(decisions)

        assert summaries["control"].mean_final_price == Decimal(150)
        assert summaries["control"].decision_count == 2
        assert summaries["treatment"].mean_final_price == Decimal(90)
        assert summaries["treatment"].decision_count == 1

    def test_mean_expected_revenue_none_when_no_model_passed(self, make_context):
        decisions = [
            _decision(
                make_context,
                "treatment",
                Decimal(200),
                metadata={"route": "JFK-LAX", "days_to_departure": 10},
            ),
        ]

        summaries = summarize_by_variant(decisions, model=None)

        assert summaries["treatment"].mean_expected_revenue is None

    def test_mean_expected_revenue_none_when_no_flight_decisions_for_variant(self, make_context):
        decisions = [_decision(make_context, "control", Decimal(100), metadata={})]

        summaries = summarize_by_variant(decisions, model=StubDemandModel())

        assert summaries["control"].mean_expected_revenue is None

    def test_mean_expected_revenue_computed_for_flight_decisions(self, make_context):
        decisions = [
            _decision(
                make_context,
                "treatment",
                Decimal(200),
                metadata={"route": "JFK-LAX", "days_to_departure": 10},
            ),
        ]

        summaries = summarize_by_variant(decisions, model=StubDemandModel())

        # StubDemandModel always predicts demand=5.0 -> revenue = 5.0 * 200
        assert summaries["treatment"].mean_expected_revenue == Decimal("1000.0")

    def test_mixed_flight_and_generic_decisions_only_averages_flight_subset(self, make_context):
        decisions = [
            _decision(make_context, "treatment", Decimal(50), metadata={}),
            _decision(
                make_context,
                "treatment",
                Decimal(200),
                metadata={"route": "JFK-LAX", "days_to_departure": 10},
            ),
        ]

        summaries = summarize_by_variant(decisions, model=StubDemandModel())

        assert summaries["treatment"].decision_count == 2
        assert summaries["treatment"].mean_expected_revenue == Decimal("1000.0")
