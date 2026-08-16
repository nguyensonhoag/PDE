"""Synthetic airline booking history — stands in for a real historical sales
warehouse (none exists in this environment). Simulates, per (route, flight),
a daily booking curve over the 120 days before departure: a ground-truth price
formula (scarcity + urgency + noise, continuous cousins of
InventoryBasedRule/TimeBasedRule) drives how many of that day's simulated
passenger arrivals actually book, given each arrival's willingness to pay.
This is what makes the resulting price/demand relationship genuinely
learnable rather than noise: higher price -> fewer bookings, and that
sensitivity (elasticity) shrinks the closer to departure.

Deterministic under a fixed seed — this is training data, not audited
financial records, so plain floats are used throughout (no Decimal
discipline); only the final elasticity number crosses back into Decimal at
the DemandElasticityRule boundary.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import date, timedelta
from math import exp

import numpy as np
import pandas as pd

from pricing_engine.config import SALES_HISTORY_PATH

CAPACITY = 300
DAYS_BEFORE_DEPARTURE = 120
FLIGHTS_PER_ROUTE = 20
BASE_DEPARTURE_DATE = date(2026, 1, 5)
WTP_FLOOR_FRACTION = 0.3
# Arrival-intensity amplitudes (leisure hump, business hump, baseline trickle).
# Larger counts than a single-aisle-realistic capacity would suggest — tuned
# empirically so daily bookings are large enough for the price/scarcity signal
# to be detectable above Poisson sampling noise at day-level granularity (see
# ml/train.py's baseline-beat gate). Not meant to be a literal capacity figure.
LEISURE_AMPLITUDE = 15.0
BUSINESS_AMPLITUDE = 22.0
BASELINE_AMPLITUDE = 2.5

ROUTE_BASE_FARES = {
    "JFK-LAX": 410.00,
    "SFO-ORD": 320.00,
    "BOS-DCA": 175.00,
    "MIA-JFK": 255.00,
    "LAX-SEA": 205.00,
}

COLUMNS = [
    "route",
    "departure_date",
    "sale_date",
    "days_to_departure",
    "seats_remaining_before",
    "seats_sold_that_day",
    "seats_remaining_after",
    "price_offered",
]


@dataclass(frozen=True)
class _DaySimResult:
    price_offered: float
    seats_sold: int


def _price_offered(base_fare: float, load_factor: float, days_to_departure: int, noise: float) -> float:
    scarcity_multiplier = 1 + 0.6 * load_factor
    urgency_multiplier = 1 + 0.4 * exp(-days_to_departure / 14)
    return round(base_fare * scarcity_multiplier * urgency_multiplier * (1 + noise), 2)

def _simulate_day(
    rng: np.random.Generator,
    base_fare: float,
    seats_remaining: int,
    days_to_departure: int,
) -> _DaySimResult:
    load_factor = 1 - seats_remaining / CAPACITY
    noise = float(np.clip(rng.normal(0, 0.03), -0.08, 0.08))
    price = _price_offered(base_fare, load_factor, days_to_departure, noise)

    arrival_intensity = (
        LEISURE_AMPLITUDE * exp(-((days_to_departure - 75) ** 2) / (2 * 20**2))
        + BUSINESS_AMPLITUDE * exp(-(days_to_departure**2) / (2 * 5**2))
        + BASELINE_AMPLITUDE
    )
    arrivals = int(rng.poisson(arrival_intensity))

    wtp_mean = base_fare * (1 + 0.8 * exp(-days_to_departure / 14))
    wtp_sigma = base_fare * (0.5 - 0.3 * exp(-days_to_departure / 14))
    wtp_floor = WTP_FLOOR_FRACTION * base_fare
    willingness_to_pay = np.clip(rng.normal(wtp_mean, wtp_sigma, size=arrivals), wtp_floor, None)

    bookings = int(np.sum(willingness_to_pay >= price))
    seats_sold = min(bookings, seats_remaining)
    return _DaySimResult(price_offered=price, seats_sold=seats_sold)


def generate_sales_history(
    routes: dict[str, float] | None = None,
    flights_per_route: int = FLIGHTS_PER_ROUTE,
    days_before_departure: int = DAYS_BEFORE_DEPARTURE,
    seed: int = 42,
) -> pd.DataFrame:
    routes = routes if routes is not None else ROUTE_BASE_FARES
    rng = np.random.default_rng(seed)
    rows: list[tuple[object, ...]] = []

    for route, base_fare in routes.items():
        for flight_index in range(flights_per_route):
            departure_date = BASE_DEPARTURE_DATE + timedelta(weeks=flight_index)
            seats_remaining = CAPACITY
            for days_to_departure in range(days_before_departure, -1, -1):
                result = _simulate_day(rng, base_fare, seats_remaining, days_to_departure)
                seats_remaining_after = seats_remaining - result.seats_sold
                sale_date = departure_date - timedelta(days=days_to_departure)
                rows.append(
                    (
                        route,
                        departure_date,
                        sale_date,
                        days_to_departure,
                        seats_remaining,
                        result.seats_sold,
                        seats_remaining_after,
                        result.price_offered,
                    )
                )
                seats_remaining = seats_remaining_after

    return pd.DataFrame(rows, columns=COLUMNS)


def main() -> None:
    df = generate_sales_history()
    output_dir = os.path.dirname(SALES_HISTORY_PATH)
    if output_dir:
        os.makedirs(output_dir, exist_ok=True)
    df.to_csv(SALES_HISTORY_PATH, index=False)
    print(f"Wrote {len(df)} rows to {SALES_HISTORY_PATH}")


if __name__ == "__main__":
    main()
