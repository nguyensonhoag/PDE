"""Thin wrapper around a trained sklearn Pipeline: predicts expected daily
demand and, from that, price elasticity via finite-difference perturbation.
Elasticity isn't modeled directly — it's derived by asking the demand model
for its prediction at the candidate price and at price*1.01, and comparing.
"""

from __future__ import annotations

from datetime import date
from typing import Any

import joblib
import pandas as pd

from pricing_engine.ml.features import engineer_features

CATEGORICAL_FEATURE_COLUMNS = ["route"]
NUMERIC_FEATURE_COLUMNS = [
    "days_to_departure",
    "seats_remaining_before",
    "price_offered",
    "load_factor",
    "price_per_seat_remaining",
    "is_last_minute",
]
# day_of_week is engineered by features.py for exploratory use but excluded
# from the model's feature set: it isn't derivable from the four scalar inputs
# available at pricing-decision time (no departure_date), and the synthetic
# simulator has no day-of-week effect to learn regardless.
MODEL_FEATURE_COLUMNS = CATEGORICAL_FEATURE_COLUMNS + NUMERIC_FEATURE_COLUMNS
TARGET_COLUMN = "seats_sold_that_day"

MIN_RELIABLE_DEMAND = 0.5
# Tree-based models are piecewise-constant, so a 1% nudge often falls inside
# the same leaf and yields an exact-zero finite difference; 10% reliably
# crosses split boundaries while staying a "local" perturbation.
ELASTICITY_PRICE_PERTURBATION = 0.10


def build_feature_row(
    route: str, days_to_departure: int, seats_remaining_before: int, price: float
) -> pd.DataFrame:
    """Build a single-row feature frame from the four scalar inputs available
    at pricing-decision time, reusing engineer_features so the derived-column
    formulas live in exactly one place. departure_date is a placeholder — only
    used internally to derive day_of_week, which is excluded from
    MODEL_FEATURE_COLUMNS below, so its actual value is irrelevant.
    """
    raw = pd.DataFrame(
        [
            {
                "route": route,
                "departure_date": date.today(),
                "days_to_departure": days_to_departure,
                "seats_remaining_before": seats_remaining_before,
                "price_offered": price,
            }
        ]
    )
    engineered = engineer_features(raw)
    return engineered[MODEL_FEATURE_COLUMNS]


class DemandModel:
    def __init__(self, pipeline: Any) -> None:
        self._pipeline = pipeline

    @classmethod
    def load(cls, path: str) -> DemandModel:
        return cls(joblib.load(path))

    def save(self, path: str) -> None:
        joblib.dump(self._pipeline, path)

    def predict_demand(
        self, route: str, days_to_departure: int, seats_remaining_before: int, price: float
    ) -> float:
        row = build_feature_row(route, days_to_departure, seats_remaining_before, price)
        prediction = self._pipeline.predict(row)[0]
        return max(float(prediction), 0.0)

    def predict_elasticity(
        self, route: str, days_to_departure: int, seats_remaining_before: int, price: float
    ) -> float | None:
        demand_at_price = self.predict_demand(
            route, days_to_departure, seats_remaining_before, price
        )
        if demand_at_price < MIN_RELIABLE_DEMAND:
            return None

        perturbed_price = price * (1 + ELASTICITY_PRICE_PERTURBATION)
        demand_at_perturbed_price = self.predict_demand(
            route, days_to_departure, seats_remaining_before, perturbed_price
        )
        pct_change_demand = (demand_at_perturbed_price - demand_at_price) / demand_at_price
        return pct_change_demand / ELASTICITY_PRICE_PERTURBATION
