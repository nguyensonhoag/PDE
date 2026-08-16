from __future__ import annotations

from decimal import Decimal

import pandas as pd

from pricing_engine.ml.backtest import BacktestResult, run_backtest
from pricing_engine.ml.rule import DemandElasticityRule
from pricing_engine.pricing.engine import PricingEngine
from pricing_engine.pricing.guardrails import MarginFloorGuardrail, MinMaxGuardrail
from pricing_engine.pricing.rules import InventoryBasedRule


class StubDemandModel:
    def predict_demand(self, route, days_to_departure, seats_remaining_before, price):
        return max(10.0 - price / 100, 0.0)

    def predict_elasticity(self, route, days_to_departure, seats_remaining_before, price):
        return -1.5


HOLDOUT_ROWS = pd.DataFrame(
    [
        {
            "route": "JFK-LAX",
            "departure_date": "2026-10-15",
            "days_to_departure": 10,
            "seats_remaining_before": 50,
            "price_offered": 400.0,
        },
        {
            "route": "SFO-ORD",
            "departure_date": "2026-10-20",
            "days_to_departure": 40,
            "seats_remaining_before": 100,
            "price_offered": 300.0,
        },
    ]
)


def _guardrails():
    return [
        MinMaxGuardrail(min_price=Decimal("10.00"), max_price=Decimal("2000.00")),
        MarginFloorGuardrail(min_margin_pct=Decimal("0.10")),
    ]


class TestRunBacktest:
    def test_returns_populated_backtest_result(self):
        model = StubDemandModel()
        engine_without_ml = PricingEngine(rules=[InventoryBasedRule()], guardrails=_guardrails())
        engine_with_ml = PricingEngine(
            rules=[InventoryBasedRule(), DemandElasticityRule(model=model)],
            guardrails=_guardrails(),
        )

        result = run_backtest(HOLDOUT_ROWS, engine_without_ml, engine_with_ml, model)

        assert isinstance(result, BacktestResult)
        assert result.rows_evaluated == 2
        assert isinstance(result.mean_price_delta_pct, Decimal)
        assert isinstance(result.mean_predicted_demand_delta, float)
