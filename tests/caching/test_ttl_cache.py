from __future__ import annotations

from pricing_engine.caching.ttl_cache import InMemoryTTLCache
from pricing_engine.pricing.models import PriceDecision


def make_decision(product_id: str, make_context) -> PriceDecision:
    context = make_context(product_id=product_id)
    return PriceDecision(
        product_id=product_id,
        base_price=context.base_price,
        final_price=context.base_price,
        rule_adjustments=(),
        guardrail_results=(),
        decided_at=context.current_time,
        context_snapshot=context,
    )


class FakeClock:
    def __init__(self, now: float = 0.0) -> None:
        self._now = now

    def __call__(self) -> float:
        return self._now

    def advance(self, seconds: float) -> None:
        self._now += seconds


class TestInMemoryTTLCache:
    def test_get_returns_none_on_miss(self):
        cache = InMemoryTTLCache(maxsize=10, ttl_seconds=60)

        assert cache.get("missing") is None

    def test_set_then_get_returns_value(self, make_context):
        cache = InMemoryTTLCache(maxsize=10, ttl_seconds=60)
        decision = make_decision("sku-1", make_context)

        cache.set("sku-1", decision)

        assert cache.get("sku-1") == decision

    def test_entry_expires_after_ttl(self, make_context):
        clock = FakeClock()
        cache = InMemoryTTLCache(maxsize=10, ttl_seconds=5, timer=clock)
        decision = make_decision("sku-1", make_context)

        cache.set("sku-1", decision)
        assert cache.get("sku-1") == decision

        clock.advance(10)

        assert cache.get("sku-1") is None

    def test_maxsize_eviction(self, make_context):
        cache = InMemoryTTLCache(maxsize=1, ttl_seconds=60)
        cache.set("sku-1", make_decision("sku-1", make_context))
        cache.set("sku-2", make_decision("sku-2", make_context))

        assert cache.get("sku-1") is None
        assert cache.get("sku-2") is not None
