from __future__ import annotations

import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.linear_model import LinearRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder

from pricing_engine.ml.model import (
    CATEGORICAL_FEATURE_COLUMNS,
    MODEL_FEATURE_COLUMNS,
    NUMERIC_FEATURE_COLUMNS,
    DemandModel,
)


def _toy_demand_model() -> DemandModel:
    """A tiny, fast, obviously-price-decreasing toy dataset — not the real
    generator — fit with plain LinearRegression so predictions are exact and
    the sign of elasticity is unambiguous for the sanity checks below."""
    rows = []
    for price in range(100, 220, 10):
        # demand decreases linearly and deterministically as price increases
        demand = max(20 - (price - 100) / 10, 0)
        rows.append(
            {
                "route": "JFK-LAX",
                "days_to_departure": 30,
                "seats_remaining_before": 100,
                "price_offered": float(price),
                "load_factor": 0.5,
                "price_per_seat_remaining": price / 100,
                "is_last_minute": 0,
                "seats_sold_that_day": demand,
            }
        )
    df = pd.DataFrame(rows)

    preprocessor = ColumnTransformer(
        [("route", OneHotEncoder(handle_unknown="ignore"), CATEGORICAL_FEATURE_COLUMNS)],
        remainder="passthrough",
    )
    pipeline = Pipeline([("preprocess", preprocessor), ("regress", LinearRegression())])
    pipeline.fit(df[MODEL_FEATURE_COLUMNS], df["seats_sold_that_day"])
    return DemandModel(pipeline)


class TestDemandModel:
    def test_predict_demand_returns_a_float(self):
        model = _toy_demand_model()

        demand = model.predict_demand("JFK-LAX", 30, 100, 150.0)

        assert isinstance(demand, float)

    def test_predict_elasticity_is_negative_for_price_decreasing_demand(self):
        model = _toy_demand_model()

        elasticity = model.predict_elasticity("JFK-LAX", 30, 100, 150.0)

        assert elasticity is not None
        assert elasticity < 0

    def test_predict_elasticity_returns_none_when_demand_is_too_low(self):
        model = _toy_demand_model()

        # price far above the toy dataset's range drives predicted demand
        # below the MIN_RELIABLE_DEMAND threshold
        elasticity = model.predict_elasticity("JFK-LAX", 30, 100, 500.0)

        assert elasticity is None

    def test_save_and_load_round_trip_preserves_predictions(self, tmp_path):
        model = _toy_demand_model()
        model_path = str(tmp_path / "model.joblib")

        model.save(model_path)
        loaded = DemandModel.load(model_path)

        original = model.predict_demand("JFK-LAX", 30, 100, 150.0)
        restored = loaded.predict_demand("JFK-LAX", 30, 100, 150.0)
        assert original == restored


def test_numeric_feature_columns_are_a_subset_of_model_feature_columns():
    assert set(NUMERIC_FEATURE_COLUMNS) <= set(MODEL_FEATURE_COLUMNS)
