"""Deterministic hash-based variant assignment for the ML-pricing A/B test.
Sticky per (experiment_id, customer_id): the same customer always lands in
the same bucket for a given experiment, with no assignment table stored
anywhere — the hash itself is the table.
"""

from __future__ import annotations

import hashlib
import os

from pricing_engine.config import DEMAND_MODEL_PATH, ENABLE_ML_PRICING

_HEX_DIGITS_USED = 8
_MAX_BUCKET = 16**_HEX_DIGITS_USED


def assign_variant(customer_id: str, experiment_id: str, treatment_split: float) -> str:
    """Deterministic bucket in [0, 1) derived from sha256(experiment_id:customer_id),
    so the same (experiment_id, customer_id) pair always maps to the same
    variant, independent of call order or process restarts.
    """
    digest = hashlib.sha256(f"{experiment_id}:{customer_id}".encode()).hexdigest()
    bucket = int(digest[:_HEX_DIGITS_USED], 16) / _MAX_BUCKET
    return "treatment" if bucket < treatment_split else "control"


def is_experiment_active() -> bool:
    """Same gate api/dependencies.py uses to decide whether the ML rule is
    even available — the experiment can never be "active" for a variant the
    engine can't actually produce.
    """
    return ENABLE_ML_PRICING and os.path.exists(DEMAND_MODEL_PATH)
