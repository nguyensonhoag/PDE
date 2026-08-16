"""Pricing endpoint: cache-check -> engine (on miss) -> persist -> cache -> return.

A cache hit is deliberately NOT re-persisted: the audit trail records decisions
made, not requests served, and a cache hit is definitionally "no new decision."

Variant assignment (control = rules-only, treatment = rules+ML) is a per-request
computation over the `customer_id` query param, not an injected singleton — see
experimentation/assignment.py's module docstring for why. When the experiment is
inactive (ENABLE_ML_PRICING off or no model file), every request is forced to
"control" regardless of customer_id, so today's default behavior is unchanged.
"""

from __future__ import annotations

import dataclasses

from fastapi import APIRouter, Depends, HTTPException

from pricing_engine.api.dependencies import (
    get_control_engine,
    get_decision_cache,
    get_decision_repository,
    get_product_source,
    get_treatment_engine,
)
from pricing_engine.caching.interfaces import DecisionCache
from pricing_engine.config import AB_TEST_EXPERIMENT_ID, AB_TEST_TREATMENT_SPLIT
from pricing_engine.datasources.interfaces import ProductDataSource
from pricing_engine.experimentation.assignment import assign_variant, is_experiment_active
from pricing_engine.persistence.repository import PriceDecisionRepository
from pricing_engine.pricing.engine import PricingEngine
from pricing_engine.pricing.serialization import decision_to_dict

router = APIRouter(prefix="/pricing", tags=["pricing"])


@router.get("/{product_id}")
def get_price(
    product_id: str,
    customer_id: str = "anonymous",
    product_source: ProductDataSource = Depends(get_product_source),
    control_engine: PricingEngine = Depends(get_control_engine),
    treatment_engine: PricingEngine = Depends(get_treatment_engine),
    cache: DecisionCache = Depends(get_decision_cache),
    repository: PriceDecisionRepository = Depends(get_decision_repository),
) -> dict[str, object]:
    try:
        context = product_source.get_pricing_context(product_id)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"unknown product_id: {product_id!r}")

    variant = (
        assign_variant(customer_id, AB_TEST_EXPERIMENT_ID, AB_TEST_TREATMENT_SPLIT)
        if is_experiment_active()
        else "control"
    )
    cache_key = f"{product_id}:{variant}"

    cached = cache.get(cache_key)
    if cached is not None:
        return decision_to_dict(cached)

    engine = treatment_engine if variant == "treatment" else control_engine
    decision = engine.decide_price(context)
    if variant == "treatment":
        decision = dataclasses.replace(decision, variant=variant)
    repository.save(decision)
    cache.set(cache_key, decision)
    return decision_to_dict(decision)
