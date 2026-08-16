"""Singleton wiring for the pricing API — the catalog store, engine, cache, and
audit-log repository are all constructed once at import time and handed out
via FastAPI `Depends`. Tests override these via `app.dependency_overrides`
instead of sharing this module's singletons across test runs.
"""

from __future__ import annotations

import os
from decimal import Decimal

from pricing_engine.caching.interfaces import DecisionCache
from pricing_engine.caching.ttl_cache import InMemoryTTLCache
from pricing_engine.catalog.db import init_db as init_catalog_db
from pricing_engine.catalog.db import make_engine as make_catalog_engine
from pricing_engine.catalog.db import make_session_factory as make_catalog_session_factory
from pricing_engine.catalog.repository import CatalogRepository
from pricing_engine.config import DEMAND_MODEL_PATH, ENABLE_ML_PRICING
from pricing_engine.datasources.interfaces import ProductDataSource
from pricing_engine.datasources.sqlite import SqliteCompetitorPriceSource, SqliteProductDataSource
from pricing_engine.persistence.db import init_db, make_engine, make_session_factory
from pricing_engine.persistence.repository import PriceDecisionRepository
from pricing_engine.pricing.engine import PricingEngine
from pricing_engine.pricing.guardrails import Guardrail, MarginFloorGuardrail, MinMaxGuardrail
from pricing_engine.pricing.rules import (
    CompetitorBasedRule,
    InventoryBasedRule,
    PricingRule,
    TimeBasedRule,
)

_catalog_engine = make_catalog_engine()
_catalog_session_factory = make_catalog_session_factory(_catalog_engine)
_catalog_repository = CatalogRepository(_catalog_session_factory)
_competitor_source = SqliteCompetitorPriceSource(_catalog_repository)
_product_source = SqliteProductDataSource(_catalog_repository, _competitor_source)

_base_rules: list[PricingRule] = [InventoryBasedRule(), TimeBasedRule(), CompetitorBasedRule()]


def _make_guardrails() -> list[Guardrail]:
    return [
        MinMaxGuardrail(min_price=Decimal("10.00"), max_price=Decimal("500.00")),
        MarginFloorGuardrail(min_margin_pct=Decimal("0.10")),
    ]


_control_engine = PricingEngine(rules=list(_base_rules), guardrails=_make_guardrails())

_treatment_rules: list[PricingRule] = list(_base_rules)
if ENABLE_ML_PRICING and os.path.exists(DEMAND_MODEL_PATH):
    # Local import, not top-of-file: keeps sklearn/pandas/joblib off the
    # import path entirely when the flag is off, mirroring pricing/rules.py's
    # "pure, dependency-free core" intent one layer up.
    from pricing_engine.ml.rule import DemandElasticityRule

    _treatment_rules.append(DemandElasticityRule())

_treatment_engine = PricingEngine(rules=_treatment_rules, guardrails=_make_guardrails())

_cache = InMemoryTTLCache()

_db_engine = make_engine()
_session_factory = make_session_factory(_db_engine)
_repository = PriceDecisionRepository(_session_factory)


def init_db_schema() -> None:
    """Create the audit-log table if it doesn't exist. Called from the app's
    startup lifespan so a fresh checkout works without a manual migration step.
    """
    init_db(_db_engine)


def init_catalog_schema() -> None:
    """Create the catalog tables if they don't exist. Does NOT load data —
    run `python -m pricing_engine.ingestion.run` separately to seed the
    catalog; keeping schema-creation and data-loading decoupled matches how a
    real batch pipeline operates independently of web-process uptime.
    """
    init_catalog_db(_catalog_engine)


def get_product_source() -> ProductDataSource:
    return _product_source


def get_control_engine() -> PricingEngine:
    return _control_engine


def get_treatment_engine() -> PricingEngine:
    return _treatment_engine


def get_decision_cache() -> DecisionCache:
    return _cache


def get_decision_repository() -> PriceDecisionRepository:
    return _repository
