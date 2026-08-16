from __future__ import annotations

from datetime import datetime
from decimal import Decimal

import pytest

from pricing_engine.persistence.db import init_db, make_engine, make_session_factory
from pricing_engine.persistence.repository import PriceDecisionRepository
from pricing_engine.pricing.models import GuardrailResult, PriceDecision, RuleAdjustment


@pytest.fixture
def repository():
    engine = make_engine("sqlite:///:memory:")
    init_db(engine)
    return PriceDecisionRepository(make_session_factory(engine))


def make_decision(make_context, **overrides) -> PriceDecision:
    context = make_context(**overrides.pop("context_overrides", {}))
    defaults = {
        "product_id": context.product_id,
        "base_price": context.base_price,
        "final_price": context.base_price * Decimal("1.1"),
        "rule_adjustments": (
            RuleAdjustment(
                rule_name="inventory_based",
                adjustment_type="multiplicative",
                value=Decimal("1.1"),
                reason="low stock",
                fired=True,
            ),
        ),
        "guardrail_results": (
            GuardrailResult(
                guardrail_name="min_max",
                passed=True,
                original_price=context.base_price * Decimal("1.1"),
                adjusted_price=context.base_price * Decimal("1.1"),
                reason="within band",
            ),
        ),
        "decided_at": datetime(2024, 1, 1, 12, 0, 0),
        "context_snapshot": context,
    }
    defaults.update(overrides)
    return PriceDecision(**defaults)


class TestPriceDecisionRepository:
    def test_save_and_retrieve_decision_roundtrips_all_fields(self, repository, make_context):
        decision = make_decision(make_context)

        repository.save(decision)
        [fetched] = repository.find_by_product(decision.product_id)

        assert fetched.product_id == decision.product_id
        assert fetched.base_price == decision.base_price
        assert fetched.final_price == decision.final_price
        assert isinstance(fetched.base_price, Decimal)
        assert fetched.rule_adjustments == decision.rule_adjustments
        assert fetched.guardrail_results == decision.guardrail_results
        assert fetched.decided_at == decision.decided_at
        assert fetched.context_snapshot == decision.context_snapshot

    def test_find_by_product_filters_by_product_id(self, repository, make_context):
        decision_a = make_decision(make_context, context_overrides={"product_id": "sku-a"})
        decision_b = make_decision(make_context, context_overrides={"product_id": "sku-b"})
        repository.save(decision_a)
        repository.save(decision_b)

        [fetched] = repository.find_by_product("sku-a")

        assert fetched.product_id == "sku-a"

    def test_find_by_product_filters_by_time_range(self, repository, make_context):
        early = make_decision(make_context, decided_at=datetime(2024, 1, 1, 0, 0, 0))
        late = make_decision(make_context, decided_at=datetime(2024, 6, 1, 0, 0, 0))
        repository.save(early)
        repository.save(late)

        results = repository.find_by_product(
            early.product_id,
            since=datetime(2024, 3, 1),
            until=datetime(2024, 12, 1),
        )

        assert [d.decided_at for d in results] == [late.decided_at]

    def test_find_by_product_unknown_product_returns_empty(self, repository):
        assert repository.find_by_product("does-not-exist") == []

    def test_save_and_retrieve_roundtrips_variant(self, repository, make_context):
        decision = make_decision(make_context, variant="treatment")

        repository.save(decision)
        [fetched] = repository.find_by_product(decision.product_id)

        assert fetched.variant == "treatment"

    def test_variant_defaults_to_control_when_not_specified(self, repository, make_context):
        decision = make_decision(make_context)

        repository.save(decision)
        [fetched] = repository.find_by_product(decision.product_id)

        assert fetched.variant == "control"


class TestFindAll:
    def test_find_all_returns_decisions_across_products(self, repository, make_context):
        decision_a = make_decision(make_context, context_overrides={"product_id": "sku-a"})
        decision_b = make_decision(make_context, context_overrides={"product_id": "sku-b"})
        repository.save(decision_a)
        repository.save(decision_b)

        results = repository.find_all()

        assert {d.product_id for d in results} == {"sku-a", "sku-b"}

    def test_find_all_filters_by_time_range(self, repository, make_context):
        early = make_decision(make_context, decided_at=datetime(2024, 1, 1, 0, 0, 0))
        late = make_decision(make_context, decided_at=datetime(2024, 6, 1, 0, 0, 0))
        repository.save(early)
        repository.save(late)

        results = repository.find_all(since=datetime(2024, 3, 1), until=datetime(2024, 12, 1))

        assert [d.decided_at for d in results] == [late.decided_at]

    def test_find_all_empty_repository_returns_empty_list(self, repository):
        assert repository.find_all() == []
