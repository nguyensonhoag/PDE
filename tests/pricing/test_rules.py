from __future__ import annotations

from datetime import datetime
from decimal import Decimal

import pytest

from pricing_engine.pricing.rules import CompetitorBasedRule, InventoryBasedRule, TimeBasedRule


class TestInventoryBasedRule:
    def test_low_stock_fires_upward(self, make_context):
        rule = InventoryBasedRule(low_stock_multiplier=Decimal("1.15"))
        context = make_context(inventory_level=5, inventory_threshold_low=10)

        adjustment = rule.evaluate(context)

        assert adjustment.fired is True
        assert adjustment.rule_name == "inventory_based"
        assert adjustment.value == Decimal("1.15")
        assert adjustment.reason

    def test_overstock_fires_downward(self, make_context):
        rule = InventoryBasedRule(overstock_multiplier=Decimal("0.90"), overstock_threshold=200)
        context = make_context(inventory_level=250)

        adjustment = rule.evaluate(context)

        assert adjustment.fired is True
        assert adjustment.value == Decimal("0.90")

    def test_normal_stock_does_not_fire(self, make_context):
        rule = InventoryBasedRule()
        context = make_context(inventory_level=50, inventory_threshold_low=10)

        adjustment = rule.evaluate(context)

        assert adjustment.fired is False
        assert adjustment.value == Decimal(1)


class TestTimeBasedRule:
    def test_peak_hour_fires(self, make_context):
        rule = TimeBasedRule(peak_hours=(17, 21), peak_multiplier=Decimal("1.10"))
        context = make_context(current_time=datetime(2024, 1, 1, 18, 0, 0))

        adjustment = rule.evaluate(context)

        assert adjustment.fired is True
        assert adjustment.value == Decimal("1.10")

    def test_off_peak_does_not_fire(self, make_context):
        rule = TimeBasedRule(peak_hours=(17, 21))
        context = make_context(current_time=datetime(2024, 1, 1, 10, 0, 0))

        adjustment = rule.evaluate(context)

        assert adjustment.fired is False

    def test_peak_window_start_is_inclusive(self, make_context):
        rule = TimeBasedRule(peak_hours=(17, 21))
        context = make_context(current_time=datetime(2024, 1, 1, 17, 0, 0))

        assert rule.evaluate(context).fired is True

    def test_peak_window_end_is_exclusive(self, make_context):
        rule = TimeBasedRule(peak_hours=(17, 21))
        context = make_context(current_time=datetime(2024, 1, 1, 21, 0, 0))

        assert rule.evaluate(context).fired is False


class TestCompetitorBasedRule:
    def test_empty_competitor_prices_does_not_fire(self, make_context):
        rule = CompetitorBasedRule(strategy="match_min")
        context = make_context(competitor_prices=())

        adjustment = rule.evaluate(context)

        assert adjustment.fired is False
        assert adjustment.value == Decimal(1)

    def test_match_min_targets_lowest_competitor(self, make_context):
        rule = CompetitorBasedRule(strategy="match_min")
        context = make_context(
            base_price=Decimal("100.00"),
            competitor_prices=(Decimal("90.00"), Decimal("95.00")),
        )

        adjustment = rule.evaluate(context)

        assert adjustment.fired is True
        assert adjustment.value == Decimal("90.00") / Decimal("100.00")

    def test_match_avg_targets_average_competitor_price(self, make_context):
        rule = CompetitorBasedRule(strategy="match_avg")
        context = make_context(
            base_price=Decimal("100.00"),
            competitor_prices=(Decimal("90.00"), Decimal("110.00")),
        )

        adjustment = rule.evaluate(context)

        assert adjustment.value == Decimal("100.00") / Decimal("100.00")

    def test_undercut_percent_targets_below_lowest_competitor(self, make_context):
        rule = CompetitorBasedRule(strategy="undercut_percent", undercut_percent=Decimal("0.10"))
        context = make_context(
            base_price=Decimal("100.00"),
            competitor_prices=(Decimal("90.00"), Decimal("95.00")),
        )

        adjustment = rule.evaluate(context)

        expected_target = Decimal("90.00") * Decimal("0.90")
        assert adjustment.value == expected_target / Decimal("100.00")

    def test_unknown_strategy_rejected_at_construction(self):
        with pytest.raises(ValueError):
            CompetitorBasedRule(strategy="nonsense")
