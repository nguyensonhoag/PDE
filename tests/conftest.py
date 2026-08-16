from __future__ import annotations

from datetime import datetime
from decimal import Decimal

import pytest

from pricing_engine.pricing.models import PricingContext


@pytest.fixture
def make_context():
    """Factory for PricingContext with sensible, overridable defaults."""

    def _make(**overrides) -> PricingContext:
        defaults = {
            "product_id": "sku-test",
            "base_price": Decimal("100.00"),
            "cost": Decimal("60.00"),
            "inventory_level": 50,
            "inventory_threshold_low": 10,
            "competitor_prices": (),
            "current_time": datetime(2024, 1, 1, 12, 0, 0),  # noon: off-peak by default
        }
        defaults.update(overrides)
        return PricingContext(**defaults)

    return _make
