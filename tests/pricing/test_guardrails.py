from __future__ import annotations

from decimal import Decimal

import pytest

from pricing_engine.pricing.guardrails import MarginFloorGuardrail, MinMaxGuardrail


class TestMinMaxGuardrail:
    def test_price_within_band_unchanged(self, make_context):
        guardrail = MinMaxGuardrail(min_price=Decimal(10), max_price=Decimal(100))
        context = make_context()

        result = guardrail.apply(Decimal(50), context)

        assert result.passed is True
        assert result.adjusted_price == Decimal(50)

    def test_price_below_min_clamped_up(self, make_context):
        guardrail = MinMaxGuardrail(min_price=Decimal(10), max_price=Decimal(100))

        result = guardrail.apply(Decimal(5), make_context())

        assert result.passed is False
        assert result.adjusted_price == Decimal(10)

    def test_price_above_max_clamped_down(self, make_context):
        guardrail = MinMaxGuardrail(min_price=Decimal(10), max_price=Decimal(100))

        result = guardrail.apply(Decimal(150), make_context())

        assert result.passed is False
        assert result.adjusted_price == Decimal(100)

    def test_boundary_prices_pass(self, make_context):
        guardrail = MinMaxGuardrail(min_price=Decimal(10), max_price=Decimal(100))
        context = make_context()

        assert guardrail.apply(Decimal(10), context).passed is True
        assert guardrail.apply(Decimal(100), context).passed is True

    def test_min_greater_than_max_rejected_at_construction(self):
        with pytest.raises(ValueError):
            MinMaxGuardrail(min_price=Decimal(100), max_price=Decimal(10))


class TestMarginFloorGuardrail:
    def test_price_above_floor_unchanged(self, make_context):
        guardrail = MarginFloorGuardrail(min_margin_pct=Decimal("0.10"))
        context = make_context(cost=Decimal(60))

        result = guardrail.apply(Decimal(100), context)

        assert result.passed is True
        assert result.adjusted_price == Decimal(100)

    def test_price_below_floor_clamped_up(self, make_context):
        guardrail = MarginFloorGuardrail(min_margin_pct=Decimal("0.10"))
        context = make_context(cost=Decimal(60))

        result = guardrail.apply(Decimal(50), context)

        assert result.passed is False
        assert result.adjusted_price == Decimal("66.0")  # 60 * 1.10

    def test_zero_cost_passes_through_unchanged(self, make_context):
        guardrail = MarginFloorGuardrail()
        context = make_context(cost=Decimal(0))

        result = guardrail.apply(Decimal(5), context)

        assert result.passed is True
        assert result.adjusted_price == Decimal(5)


class TestGuardrailPrecedence:
    def test_margin_floor_wins_when_it_conflicts_with_max(self, make_context):
        """When margin floor would push price above max, engine order (min/max then
        margin floor last) means margin floor's clamp is the one that sticks."""
        min_max = MinMaxGuardrail(min_price=Decimal(1), max_price=Decimal(50))
        margin_floor = MarginFloorGuardrail(min_margin_pct=Decimal("0.10"))
        context = make_context(cost=Decimal(60))  # floor = 66, above max of 50

        after_min_max = min_max.apply(Decimal(40), context)
        after_margin_floor = margin_floor.apply(after_min_max.adjusted_price, context)

        assert after_min_max.adjusted_price == Decimal(40)
        assert after_margin_floor.adjusted_price == Decimal("66.0")
