"""Real ProductDataSource/CompetitorPriceSource implementations, backed by the
catalog SQLite store ingestion populates. Used by the live app in place of the
in-memory mock (datasources/mock.py stays in use for fast/deterministic tests).
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

from pricing_engine.catalog.repository import CatalogRepository
from pricing_engine.datasources.interfaces import CompetitorPriceSource
from pricing_engine.pricing.models import PricingContext


class SqliteCompetitorPriceSource:
    def __init__(self, repository: CatalogRepository) -> None:
        self._repository = repository

    def get_competitor_prices(self, product_id: str) -> tuple[Decimal, ...]:
        return self._repository.get_competitor_prices(product_id)


class SqliteProductDataSource:
    def __init__(
        self, repository: CatalogRepository, competitor_source: CompetitorPriceSource
    ) -> None:
        self._repository = repository
        self._competitor_source = competitor_source

    def get_pricing_context(self, product_id: str) -> PricingContext:
        product = self._repository.get_product(product_id)  # raises KeyError if missing
        metadata: dict[str, Any] = {}
        if product.route is not None and product.departure_date is not None:
            metadata["route"] = product.route
            metadata["days_to_departure"] = (product.departure_date - date.today()).days
        return PricingContext(
            product_id=product.product_id,
            base_price=product.base_price,
            cost=product.cost,
            inventory_level=product.inventory_level,
            inventory_threshold_low=product.inventory_threshold_low,
            competitor_prices=self._competitor_source.get_competitor_prices(product_id),
            metadata=metadata,
        )
