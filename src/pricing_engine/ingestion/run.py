"""CLI entrypoint: `python -m pricing_engine.ingestion.run`. Self-sufficient —
creates the catalog schema if missing, then ingests the seed CSVs. Runnable
before or after the API has ever started, in any order.
"""

from __future__ import annotations

from pricing_engine.catalog.db import init_db, make_engine, make_session_factory
from pricing_engine.catalog.repository import CatalogRepository
from pricing_engine.ingestion.seed_loader import run_ingestion


def main() -> None:
    engine = make_engine()
    init_db(engine)
    repository = CatalogRepository(make_session_factory(engine))
    result = run_ingestion(repository)
    print(
        f"Ingested {result.products_ingested} products, "
        f"{result.competitor_prices_ingested} competitor prices."
    )


if __name__ == "__main__":
    main()
