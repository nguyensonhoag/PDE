from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from pricing_engine.catalog.db import init_db, make_engine, make_session_factory
from pricing_engine.catalog.repository import CatalogRepository


@pytest.fixture
def repository():
    engine = make_engine("sqlite:///:memory:")
    init_db(engine)
    return CatalogRepository(make_session_factory(engine))


class TestCatalogRepository:
    def test_upsert_product_creates_and_updates_by_product_id(self, repository):
        repository.upsert_product("sku-1", Decimal("49.99"), Decimal("30.00"), 5, 10)
        created = repository.get_product("sku-1")
        assert created.base_price == Decimal("49.99")
        assert created.inventory_level == 5

        repository.upsert_product("sku-1", Decimal("39.99"), Decimal("30.00"), 8, 10)
        updated = repository.get_product("sku-1")

        assert updated.base_price == Decimal("39.99")
        assert updated.inventory_level == 8

    def test_replace_competitor_prices_removes_stale_rows_on_rerun(self, repository):
        repository.upsert_product("sku-1", Decimal("49.99"), Decimal("30.00"), 5, 10)
        repository.replace_competitor_prices(
            "sku-1", [Decimal("45.00"), Decimal("52.00"), Decimal("48.00")]
        )
        assert len(repository.get_competitor_prices("sku-1")) == 3

        repository.replace_competitor_prices("sku-1", [Decimal("46.00")])
        prices = repository.get_competitor_prices("sku-1")

        assert prices == (Decimal("46.00"),)

    def test_get_product_raises_keyerror_for_unknown_product_id(self, repository):
        with pytest.raises(KeyError):
            repository.get_product("does-not-exist")

    def test_get_competitor_prices_returns_empty_tuple_when_none_seeded(self, repository):
        repository.upsert_product("sku-1", Decimal("49.99"), Decimal("30.00"), 5, 10)

        assert repository.get_competitor_prices("sku-1") == ()

    def test_upsert_product_persists_route_and_departure_date(self, repository):
        repository.upsert_product(
            "flight-jfk-lax-2026-10-15",
            Decimal("410.00"),
            Decimal("240.00"),
            42,
            15,
            route="JFK-LAX",
            departure_date=date(2026, 10, 15),
        )

        product = repository.get_product("flight-jfk-lax-2026-10-15")

        assert product.route == "JFK-LAX"
        assert product.departure_date == date(2026, 10, 15)

    def test_upsert_product_defaults_route_and_departure_date_to_none(self, repository):
        repository.upsert_product("sku-1", Decimal("49.99"), Decimal("30.00"), 5, 10)

        product = repository.get_product("sku-1")

        assert product.route is None
        assert product.departure_date is None
