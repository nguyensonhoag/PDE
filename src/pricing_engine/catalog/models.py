"""ORM schema for the product/competitor-price catalog store — the operational
data real ingestion feeds into, as opposed to persistence/models.py's opaque
audit-log blobs. Kept on its own DeclarativeBase, separate from
persistence/models.py's Base: sharing one Base would risk create_all()
creating audit-log tables in the catalog DB (or vice versa).

Competitor prices are a genuine one-to-many child table rather than a JSON
blob, since they're operational data that needs per-product replace/query,
unlike the audit log's write-once nested history.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from sqlalchemy import Date, ForeignKey, Integer, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class CatalogBase(DeclarativeBase):
    pass


class ProductRecord(CatalogBase):
    __tablename__ = "products"

    product_id: Mapped[str] = mapped_column(String, primary_key=True)
    base_price: Mapped[str] = mapped_column(String)
    cost: Mapped[str] = mapped_column(String)
    inventory_level: Mapped[int] = mapped_column(Integer)
    inventory_threshold_low: Mapped[int] = mapped_column(Integer)
    updated_at: Mapped[datetime]
    # Nullable — only populated for flight-route products (Phase 4). Blank/None
    # for the generic retail catalog from Phase 1. Must use typing.Optional, not
    # `X | None`: SQLAlchemy resolves Mapped[...] annotations at runtime via
    # eval(), and the `|` union operator isn't evaluable on Python 3.9.
    route: Mapped[Optional[str]] = mapped_column(String, nullable=True, default=None)  # noqa: UP045
    departure_date: Mapped[Optional[date]] = mapped_column(  # noqa: UP045
        Date, nullable=True, default=None
    )


class CompetitorPriceRecord(CatalogBase):
    __tablename__ = "competitor_prices"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    product_id: Mapped[str] = mapped_column(
        String, ForeignKey("products.product_id"), index=True
    )
    price: Mapped[str] = mapped_column(String)
