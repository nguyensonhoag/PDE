"""ORM schema for the price-decision audit log. Deliberately separate from
pricing/models.py: the domain dataclasses stay persistence-agnostic, and this
is the only module that knows about SQLAlchemy.

Prices are stored as strings, not floats — SQLite has no native Decimal type
and floats would silently corrupt audit data. Rule/guardrail lists are stored
as JSON rather than a child table: they're variable-length and only needed
whole for audit reconstruction, not queried individually in v1. A child table
is the natural v2 upgrade if per-rule/guardrail querying is ever needed.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Index, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class PriceDecisionRecord(Base):
    __tablename__ = "price_decisions"
    __table_args__ = (Index("ix_price_decisions_product_decided_at", "product_id", "decided_at"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    product_id: Mapped[str] = mapped_column(String, index=True)
    base_price: Mapped[str] = mapped_column(String)
    final_price: Mapped[str] = mapped_column(String)
    decided_at: Mapped[datetime] = mapped_column(index=True)
    variant: Mapped[str] = mapped_column(String, index=True, default="control")
    rule_adjustments_json: Mapped[str] = mapped_column(Text)
    guardrail_results_json: Mapped[str] = mapped_column(Text)
    context_snapshot_json: Mapped[str] = mapped_column(Text)
