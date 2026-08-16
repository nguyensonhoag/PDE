"""Repository seam between the catalog ORM tables and callers — mirrors
persistence/repository.py's contract: callers never import SQLAlchemy
directly, only this module does.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy.orm import Session, sessionmaker

from pricing_engine.catalog.models import CompetitorPriceRecord, ProductRecord


@dataclass(frozen=True)
class ProductRow:
    product_id: str
    base_price: Decimal
    cost: Decimal
    inventory_level: int
    inventory_threshold_low: int
    route: str | None = None
    departure_date: date | None = None


def _record_to_row(record: ProductRecord) -> ProductRow:
    return ProductRow(
        product_id=record.product_id,
        base_price=Decimal(record.base_price),
        cost=Decimal(record.cost),
        inventory_level=record.inventory_level,
        inventory_threshold_low=record.inventory_threshold_low,
        route=record.route,
        departure_date=record.departure_date,
    )


class CatalogRepository:
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def upsert_product(
        self,
        product_id: str,
        base_price: Decimal,
        cost: Decimal,
        inventory_level: int,
        inventory_threshold_low: int,
        route: str | None = None,
        departure_date: date | None = None,
    ) -> None:
        record = ProductRecord(
            product_id=product_id,
            base_price=str(base_price),
            cost=str(cost),
            inventory_level=inventory_level,
            inventory_threshold_low=inventory_threshold_low,
            updated_at=datetime.utcnow(),
            route=route,
            departure_date=departure_date,
        )
        with self._session_factory() as session:
            session.merge(record)
            session.commit()

    def replace_competitor_prices(self, product_id: str, prices: Sequence[Decimal]) -> None:
        with self._session_factory() as session:
            session.query(CompetitorPriceRecord).filter(
                CompetitorPriceRecord.product_id == product_id
            ).delete()
            for price in prices:
                session.add(CompetitorPriceRecord(product_id=product_id, price=str(price)))
            session.commit()

    def get_product(self, product_id: str) -> ProductRow:
        with self._session_factory() as session:
            record = session.get(ProductRecord, product_id)
            if record is None:
                raise KeyError(product_id)
            return _record_to_row(record)

    def get_competitor_prices(self, product_id: str) -> tuple[Decimal, ...]:
        with self._session_factory() as session:
            records = (
                session.query(CompetitorPriceRecord)
                .filter(CompetitorPriceRecord.product_id == product_id)
                .all()
            )
            return tuple(Decimal(r.price) for r in records)
