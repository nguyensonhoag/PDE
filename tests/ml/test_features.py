from __future__ import annotations

from datetime import date

import pandas as pd

from pricing_engine.ml.features import engineer_features

# 2026-01-05 is a Monday (day_of_week == 0)
FIXTURE = pd.DataFrame(
    [
        {
            "route": "JFK-LAX",
            "departure_date": date(2026, 1, 5),
            "sale_date": date(2026, 1, 1),
            "days_to_departure": 4,
            "seats_remaining_before": 10,
            "seats_sold_that_day": 2,
            "seats_remaining_after": 8,
            "price_offered": 500.0,
        },
        {
            "route": "SFO-ORD",
            "departure_date": date(2026, 1, 5),
            "sale_date": date(2025, 9, 8),
            "days_to_departure": 119,
            "seats_remaining_before": 0,
            "seats_sold_that_day": 0,
            "seats_remaining_after": 0,
            "price_offered": 300.0,
        },
    ]
)


class TestEngineerFeatures:
    def test_derived_columns_match_hand_computed_values(self):
        out = engineer_features(FIXTURE, capacity=150)

        first, second = out.iloc[0], out.iloc[1]

        assert first["day_of_week"] == 0
        assert first["is_last_minute"] == 1
        assert first["load_factor"] == 1 - 10 / 150
        assert first["price_per_seat_remaining"] == 500.0 / 10

        assert second["is_last_minute"] == 0
        assert second["load_factor"] == 1 - 0 / 150
        # seats_remaining_before=0 is clipped to 1 to avoid division by zero
        assert second["price_per_seat_remaining"] == 300.0 / 1

    def test_route_is_left_as_raw_string_column(self):
        out = engineer_features(FIXTURE, capacity=150)

        assert out["route"].tolist() == ["JFK-LAX", "SFO-ORD"]
        assert out["route"].dtype == object
