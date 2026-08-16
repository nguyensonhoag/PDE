from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pricing_engine.pricing.engine import PricingEngine
from pricing_engine.pricing.guardrails import MarginFloorGuardrail, MinMaxGuardrail
from pricing_engine.pricing.models import PricingContext, RuleAdjustment
from pricing_engine.pricing.rules import CompetitorBasedRule, InventoryBasedRule, TimeBasedRule


class _FixedRule:
    """Minimal PricingRule test double returning a fixed adjustment."""

    def __init__(self, name: str, adjustment_type: str, value: Decimal) -> None:
        self.name = name
        self._adjustment_type = adjustment_type
        self._value = value

    def evaluate(self, context: PricingContext) -> RuleAdjustment:
        return RuleAdjustment(
            rule_name=self.name,
            adjustment_type=self._adjustment_type,
            value=self._value,
            reason="fixed test adjustment",
            fired=True,
        )


class TestPricingEngineNoOp:
    def test_no_rules_no_guardrails_passes_through_base_price(self, make_context):
        engine = PricingEngine(rules=[], guardrails=[])
        context = make_context(base_price=Decimal("42.00"))

        decision = engine.decide_price(context)

        assert decision.final_price == Decimal("42.00")
        assert decision.rule_adjustments == ()
        assert decision.guardrail_results == ()


class TestPricingEngineFullPipeline:
    def _build_context(self, **overrides) -> PricingContext:
        defaults = {
            "product_id": "sku-1",
            "base_price": Decimal("100.00"),
            "cost": Decimal("60.00"),
            "inventory_level": 5,  # low stock -> InventoryBasedRule fires (1.15)
            "inventory_threshold_low": 10,
            "competitor_prices": (Decimal("80.00"), Decimal("85.00")),  # match_min -> 0.8
            "current_time": datetime(2024, 1, 1, 18, 0, 0),  # peak hour -> TimeBasedRule fires
        }
        defaults.update(overrides)
        return PricingContext(**defaults)

    def _build_engine(self) -> PricingEngine:
        return PricingEngine(
            rules=[
                InventoryBasedRule(low_stock_multiplier=Decimal("1.15")),
                TimeBasedRule(peak_hours=(17, 21), peak_multiplier=Decimal("1.10")),
                CompetitorBasedRule(strategy="match_min"),
            ],
            guardrails=[
                MinMaxGuardrail(min_price=Decimal(10), max_price=Decimal(200)),
                MarginFloorGuardrail(min_margin_pct=Decimal("0.10")),
            ],
        )

    def test_final_price_matches_hand_computed_value(self):
        # 100 * 1.15 * 1.10 * 0.8 = 101.2; within [10, 200] and above margin floor (66) -> unclamped
        engine = self._build_engine()
        decision = engine.decide_price(self._build_context())

        assert decision.final_price == Decimal("101.2")

    def test_all_rules_recorded_as_fired(self):
        engine = self._build_engine()
        decision = engine.decide_price(self._build_context())

        fired_names = {a.rule_name for a in decision.rule_adjustments if a.fired}
        assert fired_names == {"inventory_based", "time_based", "competitor_based"}

    def test_all_guardrails_recorded_as_passed(self):
        engine = self._build_engine()
        decision = engine.decide_price(self._build_context())

        assert all(g.passed for g in decision.guardrail_results)

    def test_non_firing_rule_still_recorded_in_audit_trail(self):
        engine = self._build_engine()
        # normal stock, off-peak, no competitor data -> nothing fires
        context = self._build_context(
            inventory_level=50,
            current_time=datetime(2024, 1, 1, 3, 0, 0),
            competitor_prices=(),
        )

        decision = engine.decide_price(context)

        assert len(decision.rule_adjustments) == 3
        assert all(a.fired is False for a in decision.rule_adjustments)
        assert decision.final_price == context.base_price

    def test_guardrail_clamp_is_reflected_in_final_price(self):
        engine = self._build_engine()
        # base_price way above max -> MinMaxGuardrail must clamp, and engine must use it
        context = self._build_context(
            base_price=Decimal("1000.00"),
            inventory_level=50,
            current_time=datetime(2024, 1, 1, 3, 0, 0),
            competitor_prices=(),
        )

        decision = engine.decide_price(context)

        assert decision.final_price == Decimal(200)  # clamped to max

    def test_context_snapshot_matches_input(self):
        engine = self._build_engine()
        context = self._build_context()

        decision = engine.decide_price(context)

        assert decision.context_snapshot == context


class TestRuleOrderMatters:
    def test_multiplicative_then_additive_differs_from_additive_then_multiplicative(
        self, make_context
    ):
        context = make_context(base_price=Decimal(100))
        multiplicative = _FixedRule("double", "multiplicative", Decimal(2))
        additive = _FixedRule("plus_ten", "additive", Decimal(10))

        mult_first = PricingEngine(rules=[multiplicative, additive], guardrails=[])
        add_first = PricingEngine(rules=[additive, multiplicative], guardrails=[])

        # (100 * 2) + 10 = 210
        assert mult_first.decide_price(context).final_price == Decimal(210)
        # (100 + 10) * 2 = 220
        assert add_first.decide_price(context).final_price == Decimal(220)
