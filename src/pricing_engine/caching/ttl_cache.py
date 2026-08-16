"""In-process TTL cache, standing in for a real Redis deployment (none available
in this environment). Wraps cachetools.TTLCache rather than hand-rolling expiry.
"""

from __future__ import annotations

from collections.abc import Callable

from cachetools import TTLCache

from pricing_engine.config import CACHE_MAXSIZE, CACHE_TTL_SECONDS
from pricing_engine.pricing.models import PriceDecision


class InMemoryTTLCache:
    def __init__(
        self,
        maxsize: int = CACHE_MAXSIZE,
        ttl_seconds: float = CACHE_TTL_SECONDS,
        timer: Callable[[], float] | None = None,
    ) -> None:
        self._cache: TTLCache[str, PriceDecision] = (
            TTLCache(maxsize=maxsize, ttl=ttl_seconds, timer=timer)
            if timer is not None
            else TTLCache(maxsize=maxsize, ttl=ttl_seconds)
        )

    def get(self, key: str) -> PriceDecision | None:
        return self._cache.get(key)

    def set(self, key: str, value: PriceDecision, ttl: int | None = None) -> None:
        # ttl is accepted for DecisionCache-interface compatibility; per-entry
        # TTL isn't supported by cachetools.TTLCache (it's cache-wide), so a
        # non-default per-call ttl is not honored here.
        self._cache[key] = value
