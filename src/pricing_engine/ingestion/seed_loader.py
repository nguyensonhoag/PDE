"""Batch ingestion: reads product/competitor-price CSV seed files and upserts
them into the catalog store. Stands in for a real vendor/warehouse connector —
swapping the CSV reader for one is the intended upgrade path, behind the same
CatalogRepository seam.
"""

from __future__ import annotations

import csv
from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from pricing_engine.catalog.repository import CatalogRepository
from pricing_engine.config import SEED_COMPETITOR_PRICES_CSV, SEED_PRODUCTS_CSV


@dataclass(frozen=True)
class IngestionResult:
    products_ingested: int
    competitor_prices_ingested: int


def run_ingestion(
    repository: CatalogRepository,
    products_path: str = SEED_PRODUCTS_CSV,
    competitor_prices_path: str = SEED_COMPETITOR_PRICES_CSV,
) -> IngestionResult:
    products_ingested = 0
    with open(products_path, newline="") as f:
        for row in csv.DictReader(f):
            route = row.get("route") or None
            departure_date_str = row.get("departure_date") or None
            repository.upsert_product(
                product_id=row["product_id"],
                base_price=Decimal(row["base_price"]),
                cost=Decimal(row["cost"]),
                inventory_level=int(row["inventory_level"]),
                inventory_threshold_low=int(row["inventory_threshold_low"]),
                route=route,
                departure_date=date.fromisoformat(departure_date_str)
                if departure_date_str
                else None,
            )
            products_ingested += 1

    prices_by_product: dict[str, list[Decimal]] = defaultdict(list)
    with open(competitor_prices_path, newline="") as f:
        for row in csv.DictReader(f):
            prices_by_product[row["product_id"]].append(Decimal(row["price"]))

    competitor_prices_ingested = 0
    for product_id, prices in prices_by_product.items():
        repository.replace_competitor_prices(product_id, prices)
        competitor_prices_ingested += len(prices)

    return IngestionResult(
        products_ingested=products_ingested,
        competitor_prices_ingested=competitor_prices_ingested,
    )
