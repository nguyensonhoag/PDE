"""Contracts future real ingestion (Phase 1) will implement. Mocks in mock.py and any
future real implementation are interchangeable via structural typing, no inheritance
required.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Protocol

from pricing_engine.pricing.models import PricingContext


class ProductDataSource(Protocol):
    def get_pricing_context(self, product_id: str) -> PricingContext: ...


class CompetitorPriceSource(Protocol):
    def get_competitor_prices(self, product_id: str) -> tuple[Decimal, ...]: ...
