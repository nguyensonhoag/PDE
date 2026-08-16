"""TEST-ONLY DATA SOURCE — NOT USED BY THE LIVE APP.

Hardcoded in-memory catalog for fast, deterministic tests. The live app uses
datasources/sqlite.py, backed by real ingestion (see ingestion/seed_loader.py).
"""

from __future__ import annotations

from decimal import Decimal

from pricing_engine.pricing.models import PricingContext


class InMemoryProductDataSource:
    def __init__(self, catalog: dict[str, PricingContext] | None = None) -> None:
        self._catalog = catalog if catalog is not None else {}

    def get_pricing_context(self, product_id: str) -> PricingContext:
        return self._catalog[product_id]


class InMemoryCompetitorPriceSource:
    def __init__(self, prices: dict[str, tuple[Decimal, ...]] | None = None) -> None:
        self._prices = prices if prices is not None else {}

    def get_competitor_prices(self, product_id: str) -> tuple[Decimal, ...]:
        return self._prices.get(product_id, ())
