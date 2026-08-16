"""Feature engineering for the demand model. Operates on the raw sales-history
DataFrame (generate_sales_history.py's schema, whether freshly generated or
reloaded from CSV). `route` is deliberately left as a raw string column here —
one-hot encoding happens inside the sklearn Pipeline (train.py), not here, so
the encoding logic lives in exactly one place.
"""

from __future__ import annotations

import pandas as pd

from pricing_engine.ml.generate_sales_history import CAPACITY

LAST_MINUTE_THRESHOLD_DAYS = 7


def engineer_features(df: pd.DataFrame, capacity: int = CAPACITY) -> pd.DataFrame:
    out = df.copy()
    out["day_of_week"] = pd.to_datetime(out["departure_date"]).dt.dayofweek
    out["is_last_minute"] = (out["days_to_departure"] <= LAST_MINUTE_THRESHOLD_DAYS).astype(int)
    out["load_factor"] = 1 - out["seats_remaining_before"] / capacity
    out["price_per_seat_remaining"] = out["price_offered"] / out["seats_remaining_before"].clip(
        lower=1
    )
    return out
