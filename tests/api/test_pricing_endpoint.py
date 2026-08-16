from __future__ import annotations

from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from pricing_engine.api.dependencies import (
    get_control_engine,
    get_decision_cache,
    get_decision_repository,
    get_product_source,
    get_treatment_engine,
)
from pricing_engine.api.main import app
from pricing_engine.caching.ttl_cache import InMemoryTTLCache
from pricing_engine.config import AB_TEST_EXPERIMENT_ID, AB_TEST_TREATMENT_SPLIT
from pricing_engine.datasources.mock import InMemoryProductDataSource
from pricing_engine.experimentation import assignment
from pricing_engine.experimentation.assignment import assign_variant
from pricing_engine.ml.rule import DemandElasticityRule
from pricing_engine.persistence.db import init_db, make_engine, make_session_factory
from pricing_engine.persistence.repository import PriceDecisionRepository
from pricing_engine.pricing.engine import PricingEngine
from pricing_engine.pricing.guardrails import MarginFloorGuardrail, MinMaxGuardrail
from pricing_engine.pricing.models import PricingContext
from pricing_engine.pricing.rules import CompetitorBasedRule, InventoryBasedRule, TimeBasedRule


class CountingPricingEngine(PricingEngine):
    """Delegates to a real PricingEngine but counts decide_price calls, so tests
    can assert a cache hit skipped recomputation without relying on internals."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.call_count = 0

    def decide_price(self, context):
        self.call_count += 1
        return super().decide_price(context)


class StubDemandModel:
    """Fixed elasticity regardless of inputs — avoids depending on a real
    trained joblib artifact in unit tests."""

    def predict_elasticity(self, route, days_to_departure, seats_remaining_before, price):
        return -3.5  # highly elastic -> the rule's multiplier floor (0.85), deterministically

    def predict_demand(self, route, days_to_departure, seats_remaining_before, price):
        return 10.0


@pytest.fixture
def test_catalog():
    return {
        "sku-1": PricingContext(
            product_id="sku-1",
            base_price=Decimal("49.99"),
            cost=Decimal("30.00"),
            inventory_level=5,
            competitor_prices=(Decimal("45.00"), Decimal("52.00")),
        ),
        "flight-jfk-lax-test": PricingContext(
            product_id="flight-jfk-lax-test",
            base_price=Decimal("200.00"),
            cost=Decimal("120.00"),
            inventory_level=50,
            metadata={"route": "JFK-LAX", "days_to_departure": 10},
        ),
    }


@pytest.fixture
def test_engine(test_catalog):
    return CountingPricingEngine(
        rules=[InventoryBasedRule(), TimeBasedRule(), CompetitorBasedRule()],
        guardrails=[
            MinMaxGuardrail(min_price=Decimal("10.00"), max_price=Decimal("500.00")),
            MarginFloorGuardrail(min_margin_pct=Decimal("0.10")),
        ],
    )


@pytest.fixture
def test_treatment_engine():
    return CountingPricingEngine(
        rules=[
            InventoryBasedRule(),
            TimeBasedRule(),
            CompetitorBasedRule(),
            DemandElasticityRule(model=StubDemandModel()),
        ],
        guardrails=[
            MinMaxGuardrail(min_price=Decimal("10.00"), max_price=Decimal("500.00")),
            MarginFloorGuardrail(min_margin_pct=Decimal("0.10")),
        ],
    )


@pytest.fixture
def test_repository():
    engine = make_engine("sqlite:///:memory:")
    init_db(engine)
    return PriceDecisionRepository(make_session_factory(engine))


@pytest.fixture
def client(test_catalog, test_engine, test_treatment_engine, test_repository):
    test_cache = InMemoryTTLCache(maxsize=10, ttl_seconds=60)
    app.dependency_overrides[get_product_source] = lambda: InMemoryProductDataSource(test_catalog)
    app.dependency_overrides[get_control_engine] = lambda: test_engine
    app.dependency_overrides[get_treatment_engine] = lambda: test_treatment_engine
    app.dependency_overrides[get_decision_cache] = lambda: test_cache
    app.dependency_overrides[get_decision_repository] = lambda: test_repository
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def _find_customer_id_for(variant: str, start: int = 0) -> str:
    """Brute-force search for a customer_id that deterministically lands in
    the given variant (using the same experiment id/split the route uses),
    rather than hardcoding fragile literals."""
    i = start
    while True:
        candidate = f"customer-{i}"
        if (
            assign_variant(candidate, AB_TEST_EXPERIMENT_ID, AB_TEST_TREATMENT_SPLIT)
            == variant
        ):
            return candidate
        i += 1


def test_known_product_returns_200_with_audit_trail(client):
    response = client.get("/pricing/sku-1")

    assert response.status_code == 200
    body = response.json()
    assert body["product_id"] == "sku-1"
    assert "final_price" in body
    assert "rule_adjustments" in body
    assert "guardrail_results" in body
    assert len(body["rule_adjustments"]) > 0


def test_unknown_product_returns_404(client):
    response = client.get("/pricing/does-not-exist")

    assert response.status_code == 404


class TestPricingEndpointCaching:
    def test_cache_miss_computes_new_decision(self, client, test_engine):
        response = client.get("/pricing/sku-1")

        assert response.status_code == 200
        assert test_engine.call_count == 1

    def test_second_request_for_same_product_is_served_from_cache(self, client, test_engine):
        first = client.get("/pricing/sku-1")
        second = client.get("/pricing/sku-1")

        assert first.json() == second.json()
        assert test_engine.call_count == 1

    def test_decision_is_persisted_on_cache_miss(self, client, test_repository):
        client.get("/pricing/sku-1")

        decisions = test_repository.find_by_product("sku-1")

        assert len(decisions) == 1
        assert decisions[0].product_id == "sku-1"

    def test_cache_hit_does_not_create_duplicate_persisted_row(self, client, test_repository):
        client.get("/pricing/sku-1")
        client.get("/pricing/sku-1")

        decisions = test_repository.find_by_product("sku-1")

        assert len(decisions) == 1

    def test_unknown_product_does_not_persist_or_cache(self, client, test_repository, test_engine):
        client.get("/pricing/does-not-exist")

        assert test_repository.find_by_product("does-not-exist") == []
        assert test_engine.call_count == 0


@pytest.fixture
def experiment_active(monkeypatch, tmp_path):
    """Makes is_experiment_active() return True. Patches the names bound
    inside experimentation.assignment's own namespace — patching
    pricing_engine.config directly would NOT work, since `from
    pricing_engine.config import ENABLE_ML_PRICING` binds a copy of the name
    into assignment's namespace at import time, not a live re-read."""
    model_path = tmp_path / "model.joblib"
    model_path.write_text("stub")
    monkeypatch.setattr(assignment, "ENABLE_ML_PRICING", True)
    monkeypatch.setattr(assignment, "DEMAND_MODEL_PATH", str(model_path))


class TestPricingEndpointExperimentation:
    def test_experiment_inactive_forces_control_regardless_of_customer_id(
        self, client, test_treatment_engine
    ):
        response = client.get("/pricing/sku-1?customer_id=anyone")

        assert response.json()["variant"] == "control"
        assert test_treatment_engine.call_count == 0

    def test_sticky_assignment_same_customer_same_variant(self, client, experiment_active):
        customer_id = _find_customer_id_for("treatment")

        first = client.get(f"/pricing/flight-jfk-lax-test?customer_id={customer_id}")
        second = client.get(f"/pricing/flight-jfk-lax-test?customer_id={customer_id}")

        assert first.json()["variant"] == "treatment"
        assert second.json()["variant"] == "treatment"

    def test_treatment_and_control_customers_get_different_prices_for_flight_product(
        self, client, experiment_active
    ):
        control_customer = _find_customer_id_for("control")
        treatment_customer = _find_customer_id_for("treatment")

        control_response = client.get(
            f"/pricing/flight-jfk-lax-test?customer_id={control_customer}"
        )
        treatment_response = client.get(
            f"/pricing/flight-jfk-lax-test?customer_id={treatment_customer}"
        )

        assert control_response.json()["variant"] == "control"
        assert treatment_response.json()["variant"] == "treatment"
        assert control_response.json()["final_price"] != treatment_response.json()["final_price"]

    def test_cache_not_shared_across_variants_for_same_product(
        self, client, experiment_active, test_engine, test_treatment_engine
    ):
        control_customer = _find_customer_id_for("control")
        treatment_customer = _find_customer_id_for("treatment")

        client.get(f"/pricing/flight-jfk-lax-test?customer_id={control_customer}")
        client.get(f"/pricing/flight-jfk-lax-test?customer_id={treatment_customer}")

        assert test_engine.call_count == 1
        assert test_treatment_engine.call_count == 1

    def test_decisions_persisted_with_correct_variant_tag(
        self, client, experiment_active, test_repository
    ):
        control_customer = _find_customer_id_for("control")
        treatment_customer = _find_customer_id_for("treatment")

        client.get(f"/pricing/flight-jfk-lax-test?customer_id={control_customer}")
        client.get(f"/pricing/flight-jfk-lax-test?customer_id={treatment_customer}")

        decisions = test_repository.find_by_product("flight-jfk-lax-test")
        variants = {d.variant for d in decisions}

        assert variants == {"control", "treatment"}
