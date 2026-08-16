"""Cache contract for serving PriceDecisions. Mirrors the structural-typing
Protocol style already used in datasources/interfaces.py — a future Redis-backed
implementation just needs to satisfy this shape, no inheritance required.
"""

from __future__ import annotations

from typing import Protocol

from pricing_engine.pricing.models import PriceDecision


class DecisionCache(Protocol):
    def get(self, key: str) -> PriceDecision | None: ...

    def set(self, key: str, value: PriceDecision, ttl: int | None = None) -> None: ...
