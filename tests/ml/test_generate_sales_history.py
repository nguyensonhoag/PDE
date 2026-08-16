from __future__ import annotations

from pricing_engine.ml.generate_sales_history import COLUMNS, generate_sales_history


class TestGenerateSalesHistory:
    def test_output_is_deterministic_under_fixed_seed(self):
        first = generate_sales_history(flights_per_route=2, seed=42)
        second = generate_sales_history(flights_per_route=2, seed=42)

        assert first.equals(second)

    def test_output_has_expected_schema_and_row_count(self):
        df = generate_sales_history(flights_per_route=2)

        assert list(df.columns) == COLUMNS
        # 5 routes * 2 flights * 121 days-before-departure (120..0 inclusive)
        assert len(df) == 5 * 2 * 121

    def test_never_sells_more_seats_than_remaining(self):
        df = generate_sales_history(flights_per_route=5)

        assert (df.seats_sold_that_day <= df.seats_remaining_before).all()

    def test_inventory_is_conserved_across_consecutive_days(self):
        df = generate_sales_history(flights_per_route=5)

        assert (
            df.seats_remaining_after == df.seats_remaining_before - df.seats_sold_that_day
        ).all()

        for _, flight_df in df.groupby(["route", "departure_date"]):
            flight_df = flight_df.sort_values("days_to_departure", ascending=False)
            carried = flight_df.seats_remaining_after.iloc[:-1].to_numpy()
            next_before = flight_df.seats_remaining_before.iloc[1:].to_numpy()
            assert (carried == next_before).all()

    def test_price_is_higher_when_inventory_is_scarce_same_days_to_departure_bucket(self):
        df = generate_sales_history(flights_per_route=20)
        window = df[(df.days_to_departure >= 40) & (df.days_to_departure <= 60)]
        median_seats = window.seats_remaining_before.median()

        scarce = window[window.seats_remaining_before < median_seats]
        plentiful = window[window.seats_remaining_before >= median_seats]

        assert scarce.price_offered.mean() > plentiful.price_offered.mean()
