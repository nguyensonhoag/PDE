"""Trains the demand model against (synthetic) historical sales and gates
persistence on beating a naive baseline — a real, meaningful check, not a
smoke test. CLI entrypoint: `python -m pricing_engine.ml.train`.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass

import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.dummy import DummyRegressor
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.metrics import mean_absolute_error
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder

from pricing_engine.config import DEMAND_MODEL_PATH, SALES_HISTORY_PATH
from pricing_engine.ml.features import engineer_features
from pricing_engine.ml.model import (
    CATEGORICAL_FEATURE_COLUMNS,
    MODEL_FEATURE_COLUMNS,
    NUMERIC_FEATURE_COLUMNS,
    TARGET_COLUMN,
    DemandModel,
)

# Column names ColumnTransformer produces for the passthrough numeric block
# when given an explicit transformer name (instead of the "remainder" bucket)
# with pandas output — used to target monotonic constraints precisely below.
_PRICE_COLUMN = "numeric__price_offered"
_PRICE_PER_SEAT_COLUMN = "numeric__price_per_seat_remaining"

HOLDOUT_FRACTION = 0.2
BASELINE_IMPROVEMENT_THRESHOLD = 0.8  # model must beat baseline MAE by >= 20%


@dataclass(frozen=True)
class TrainResult:
    model: DemandModel
    model_mae: float
    baseline_mae: float

    @property
    def beats_baseline(self) -> bool:
        return self.model_mae <= self.baseline_mae * BASELINE_IMPROVEMENT_THRESHOLD


def chronological_holdout_split(
    df: pd.DataFrame, holdout_fraction: float = HOLDOUT_FRACTION
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Split by departure_date within each route (last `holdout_fraction` of
    departures per route go to holdout) rather than a random row split — a
    random split would leak the same flight's early-window rows into train
    and late-window rows into test, which is unrealistically easy.
    """
    train_parts = []
    holdout_parts = []
    for _route, route_df in df.groupby("route"):
        departure_dates = sorted(route_df["departure_date"].unique())
        split_index = max(1, int(len(departure_dates) * (1 - holdout_fraction)))
        holdout_dates = set(departure_dates[split_index:])
        is_holdout = route_df["departure_date"].isin(holdout_dates)
        train_parts.append(route_df[~is_holdout])
        holdout_parts.append(route_df[is_holdout])
    return pd.concat(train_parts, ignore_index=True), pd.concat(holdout_parts, ignore_index=True)


def _build_pipeline() -> Pipeline:
    # Explicit "numeric" transformer name (rather than the special "remainder"
    # bucket) so pandas output gives deterministic, addressable column names
    # for the monotonic constraint below.
    preprocessor = ColumnTransformer(
        [
            (
                "route",
                OneHotEncoder(handle_unknown="ignore", sparse_output=False),
                CATEGORICAL_FEATURE_COLUMNS,
            ),
            ("numeric", "passthrough", NUMERIC_FEATURE_COLUMNS),
        ]
    )
    preprocessor.set_output(transform="pandas")

    # Demand must be non-increasing in price and in price-per-remaining-seat
    # (which moves with price) — without this, an unconstrained ensemble can
    # (and did, empirically) predict demand *rising* with price in some
    # regions, which would hand DemandElasticityRule a backwards signal.
    # Everything else is left unconstrained.
    monotonic_constraints = {_PRICE_COLUMN: -1, _PRICE_PER_SEAT_COLUMN: -1}
    regressor = HistGradientBoostingRegressor(
        max_iter=200, random_state=42, monotonic_cst=monotonic_constraints
    )
    return Pipeline([("preprocess", preprocessor), ("regress", regressor)])


def train_and_evaluate(df: pd.DataFrame) -> TrainResult:
    engineered = engineer_features(df)
    train_df, holdout_df = chronological_holdout_split(engineered)

    X_train = train_df[MODEL_FEATURE_COLUMNS]
    y_train = train_df[TARGET_COLUMN]
    X_holdout = holdout_df[MODEL_FEATURE_COLUMNS]
    y_holdout = holdout_df[TARGET_COLUMN]

    pipeline = _build_pipeline()
    pipeline.fit(X_train, y_train)
    model_mae = mean_absolute_error(y_holdout, pipeline.predict(X_holdout))

    baseline = DummyRegressor(strategy="mean")
    baseline.fit(X_train, y_train)
    baseline_mae = mean_absolute_error(y_holdout, baseline.predict(X_holdout))

    return TrainResult(model=DemandModel(pipeline), model_mae=model_mae, baseline_mae=baseline_mae)


def main() -> None:
    df = pd.read_csv(SALES_HISTORY_PATH, parse_dates=["departure_date", "sale_date"])
    result = train_and_evaluate(df)

    print(f"model MAE: {result.model_mae:.3f}, baseline MAE: {result.baseline_mae:.3f}")
    if not result.beats_baseline:
        print(
            f"Model does not beat baseline by the required "
            f"{(1 - BASELINE_IMPROVEMENT_THRESHOLD):.0%} margin — refusing to save."
        )
        sys.exit(1)

    output_dir = os.path.dirname(DEMAND_MODEL_PATH)
    if output_dir:
        os.makedirs(output_dir, exist_ok=True)
    result.model.save(DEMAND_MODEL_PATH)
    print(f"Saved model to {DEMAND_MODEL_PATH}")


if __name__ == "__main__":
    main()
