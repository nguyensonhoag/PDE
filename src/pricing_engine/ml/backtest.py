"""Compares rules-only vs. rules+ML pricing decisions over held-out historical
rows. NOTE: evaluating against the same model used to price is circular for
synthetic data — this is a directional sanity check (does the ML rule move
price/predicted-demand the way we'd expect?), not an independent validation.
A real backtest needs real, independently-observed outcomes, which don't
exist for a synthetic dataset by construction.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any

import pandas as pd

from pricing_engine.ml.model import DemandModel
from pricing_engine.pricing.engine import PricingEngine
from pricing_engine.pricing.models import PricingContext

DEFAULT_COST_FRACTION = Decimal("0.6")
DEFAULT_INVENTORY_THRESHOLD_LOW = 10


@dataclass(frozen=True)
class BacktestResult:
    rows_evaluated: int
    mean_price_delta_pct: Decimal
    mean_predicted_demand_delta: float


def _context_from_row(row: pd.Series[Any]) -> PricingContext:
    base_price = Decimal(str(row["price_offered"]))
    return PricingContext(
        product_id=f"{row['route']}-{row['departure_date']}",
        base_price=base_price,
        cost=base_price * DEFAULT_COST_FRACTION,
        inventory_level=int(row["seats_remaining_before"]),
        inventory_threshold_low=DEFAULT_INVENTORY_THRESHOLD_LOW,
        metadata={"route": row["route"], "days_to_departure": int(row["days_to_departure"])},
    )


def run_backtest(
    holdout_df: pd.DataFrame,
    engine_without_ml: PricingEngine,
    engine_with_ml: PricingEngine,
    model: DemandModel,
) -> BacktestResult:
    price_deltas: list[Decimal] = []
    demand_deltas: list[float] = []

    for _, row in holdout_df.iterrows():
        context = _context_from_row(row)
        decision_without = engine_without_ml.decide_price(context)
        decision_with = engine_with_ml.decide_price(context)

        if decision_without.final_price != 0:
            price_deltas.append(
                (decision_with.final_price - decision_without.final_price)
                / decision_without.final_price
            )

        route = str(row["route"])
        days_to_departure = int(row["days_to_departure"])
        seats_remaining_before = int(row["seats_remaining_before"])
        demand_without = model.predict_demand(
            route, days_to_departure, seats_remaining_before, float(decision_without.final_price)
        )
        demand_with = model.predict_demand(
            route, days_to_departure, seats_remaining_before, float(decision_with.final_price)
        )
        demand_deltas.append(demand_with - demand_without)

    mean_price_delta_pct = (
        sum(price_deltas, Decimal(0)) / Decimal(len(price_deltas)) if price_deltas else Decimal(0)
    )
    mean_predicted_demand_delta = (
        sum(demand_deltas) / len(demand_deltas) if demand_deltas else 0.0
    )

    return BacktestResult(
        rows_evaluated=len(holdout_df),
        mean_price_delta_pct=mean_price_delta_pct,
        mean_predicted_demand_delta=mean_predicted_demand_delta,
    )
