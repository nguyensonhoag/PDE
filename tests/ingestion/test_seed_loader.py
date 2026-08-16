from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from pricing_engine.catalog.db import init_db, make_engine, make_session_factory
from pricing_engine.catalog.repository import CatalogRepository
from pricing_engine.ingestion.seed_loader import run_ingestion

PRODUCTS_CSV = """product_id,base_price,cost,inventory_level,inventory_threshold_low
sku-a,10.00,5.00,50,10
sku-b,20.00,12.00,3,10
"""

COMPETITOR_PRICES_CSV = """product_id,price
sku-a,9.50
sku-a,10.50
sku-b,19.00
"""


@pytest.fixture
def repository():
    engine = make_engine("sqlite:///:memory:")
    init_db(engine)
    return CatalogRepository(make_session_factory(engine))


@pytest.fixture
def seed_files(tmp_path):
    products_path = tmp_path / "products.csv"
    competitor_prices_path = tmp_path / "competitor_prices.csv"
    products_path.write_text(PRODUCTS_CSV)
    competitor_prices_path.write_text(COMPETITOR_PRICES_CSV)
    return str(products_path), str(competitor_prices_path)


class TestRunIngestion:
    def test_ingests_products_from_seed_csv(self, repository, seed_files):
        products_path, competitor_prices_path = seed_files

        result = run_ingestion(repository, products_path, competitor_prices_path)

        assert result.products_ingested == 2
        product = repository.get_product("sku-a")
        assert product.base_price == Decimal("10.00")
        assert product.inventory_level == 50

    def test_ingests_competitor_prices_one_row_per_price(self, repository, seed_files):
        products_path, competitor_prices_path = seed_files

        result = run_ingestion(repository, products_path, competitor_prices_path)

        assert result.competitor_prices_ingested == 3
        assert repository.get_competitor_prices("sku-a") == (Decimal("9.50"), Decimal("10.50"))

    def test_rerunning_ingestion_is_idempotent_no_duplicate_competitor_rows(
        self, repository, seed_files
    ):
        products_path, competitor_prices_path = seed_files

        run_ingestion(repository, products_path, competitor_prices_path)
        run_ingestion(repository, products_path, competitor_prices_path)

        assert len(repository.get_competitor_prices("sku-a")) == 2

    def test_rerunning_ingestion_updates_changed_product_fields(
        self, repository, seed_files, tmp_path
    ):
        products_path, competitor_prices_path = seed_files
        run_ingestion(repository, products_path, competitor_prices_path)

        updated_products_path = tmp_path / "products_updated.csv"
        updated_products_path.write_text(
            "product_id,base_price,cost,inventory_level,inventory_threshold_low\n"
            "sku-a,11.00,5.00,40,10\n"
            "sku-b,20.00,12.00,3,10\n"
        )
        run_ingestion(repository, str(updated_products_path), competitor_prices_path)

        product = repository.get_product("sku-a")
        assert product.base_price == Decimal("11.00")
        assert product.inventory_level == 40

    def test_ingests_optional_route_and_departure_date_columns(self, repository, tmp_path):
        products_path = tmp_path / "products_with_flights.csv"
        products_path.write_text(
            "product_id,base_price,cost,inventory_level,inventory_threshold_low,"
            "route,departure_date\n"
            "sku-a,10.00,5.00,50,10,,\n"
            "flight-jfk-lax-2026-10-15,410.00,240.00,42,15,JFK-LAX,2026-10-15\n"
        )
        competitor_prices_path = tmp_path / "empty_competitor_prices.csv"
        competitor_prices_path.write_text("product_id,price\n")

        run_ingestion(repository, str(products_path), str(competitor_prices_path))

        generic = repository.get_product("sku-a")
        assert generic.route is None
        assert generic.departure_date is None

        flight = repository.get_product("flight-jfk-lax-2026-10-15")
        assert flight.route == "JFK-LAX"
        assert flight.departure_date == date(2026, 10, 15)
