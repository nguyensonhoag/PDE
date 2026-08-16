from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import pytest

from pricing_engine.catalog.db import init_db, make_engine, make_session_factory
from pricing_engine.catalog.repository import CatalogRepository
from pricing_engine.datasources.sqlite import SqliteCompetitorPriceSource, SqliteProductDataSource


@pytest.fixture
def repository():
    engine = make_engine("sqlite:///:memory:")
    init_db(engine)
    return CatalogRepository(make_session_factory(engine))


@pytest.fixture
def competitor_source(repository):
    return SqliteCompetitorPriceSource(repository)


@pytest.fixture
def product_source(repository, competitor_source):
    return SqliteProductDataSource(repository, competitor_source)


class TestSqliteProductDataSource:
    def test_get_pricing_context_returns_context_with_composed_competitor_prices(
        self, repository, product_source
    ):
        repository.upsert_product("sku-1", Decimal("49.99"), Decimal("30.00"), 5, 10)
        repository.replace_competitor_prices("sku-1", [Decimal("45.00"), Decimal("52.00")])

        context = product_source.get_pricing_context("sku-1")

        assert context.product_id == "sku-1"
        assert context.base_price == Decimal("49.99")
        assert context.cost == Decimal("30.00")
        assert context.inventory_level == 5
        assert context.inventory_threshold_low == 10
        assert context.competitor_prices == (Decimal("45.00"), Decimal("52.00"))

    def test_get_pricing_context_raises_keyerror_for_unknown_product(self, product_source):
        with pytest.raises(KeyError):
            product_source.get_pricing_context("does-not-exist")

    def test_get_pricing_context_returns_empty_competitor_prices_when_none_seeded(
        self, repository, product_source
    ):
        repository.upsert_product("sku-9", Decimal("34.99"), Decimal("20.00"), 0, 10)

        context = product_source.get_pricing_context("sku-9")

        assert context.competitor_prices == ()

    def test_get_pricing_context_populates_metadata_for_flight_products(
        self, repository, product_source
    ):
        departure_date = date.today() + timedelta(days=14)
        repository.upsert_product(
            "flight-jfk-lax-2026-10-15",
            Decimal("410.00"),
            Decimal("240.00"),
            42,
            15,
            route="JFK-LAX",
            departure_date=departure_date,
        )

        context = product_source.get_pricing_context("flight-jfk-lax-2026-10-15")

        assert context.metadata == {"route": "JFK-LAX", "days_to_departure": 14}

    def test_get_pricing_context_leaves_metadata_empty_for_generic_products(
        self, repository, product_source
    ):
        repository.upsert_product("sku-1", Decimal("49.99"), Decimal("30.00"), 5, 10)

        context = product_source.get_pricing_context("sku-1")

        assert context.metadata == {}


class TestSqliteCompetitorPriceSource:
    def test_get_competitor_prices_returns_empty_tuple_for_unknown_product(
        self, competitor_source
    ):
        assert competitor_source.get_competitor_prices("does-not-exist") == ()
