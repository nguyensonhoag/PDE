"""Cross-product variant metrics report for the ML-pricing A/B test. Not a
dashboard — a CLI report over the existing audit log. mean_expected_revenue is
a synthetic proxy (Phase 4's DemandModel prediction * price), not a real
revenue measurement: no conversion/purchase event exists anywhere in this
system to measure against, same honest-scoping choice as every prior phase's
synthetic-data decisions.
"""

from __future__ import annotations

import os
from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal

from pricing_engine.config import DEMAND_MODEL_PATH
from pricing_engine.ml.model import DemandModel
from pricing_engine.persistence.db import make_engine, make_session_factory
from pricing_engine.persistence.repository import PriceDecisionRepository
from pricing_engine.pricing.models import PriceDecision


@dataclass(frozen=True)
class VariantSummary:
    variant: str
    decision_count: int
    mean_final_price: Decimal
    mean_expected_revenue: Decimal | None


def _is_flight_decision(decision: PriceDecision) -> bool:
    metadata = decision.context_snapshot.metadata
    return metadata.get("route") is not None and metadata.get("days_to_departure") is not None


def _expected_revenue(decision: PriceDecision, model: DemandModel) -> Decimal:
    demand = model.predict_demand(
        route=decision.context_snapshot.metadata["route"],
        days_to_departure=decision.context_snapshot.metadata["days_to_departure"],
        seats_remaining_before=decision.context_snapshot.inventory_level,
        price=float(decision.final_price),
    )
    return Decimal(str(demand)) * decision.final_price


def summarize_by_variant(
    decisions: Sequence[PriceDecision], model: DemandModel | None = None
) -> dict[str, VariantSummary]:
    by_variant: dict[str, list[PriceDecision]] = {}
    for d in decisions:
        by_variant.setdefault(d.variant, []).append(d)

    summaries: dict[str, VariantSummary] = {}
    for variant, group in by_variant.items():
        mean_final_price = sum((d.final_price for d in group), Decimal(0)) / Decimal(len(group))

        mean_expected_revenue: Decimal | None = None
        if model is not None:
            flight_decisions = [d for d in group if _is_flight_decision(d)]
            if flight_decisions:
                revenues = [_expected_revenue(d, model) for d in flight_decisions]
                mean_expected_revenue = sum(revenues, Decimal(0)) / Decimal(len(revenues))

        summaries[variant] = VariantSummary(
            variant=variant,
            decision_count=len(group),
            mean_final_price=mean_final_price,
            mean_expected_revenue=mean_expected_revenue,
        )
    return summaries


def main() -> None:
    engine = make_engine()
    repository = PriceDecisionRepository(make_session_factory(engine))
    decisions = repository.find_all()

    model = DemandModel.load(DEMAND_MODEL_PATH) if os.path.exists(DEMAND_MODEL_PATH) else None
    summaries = summarize_by_variant(decisions, model=model)

    print(f"{'variant':<12}{'count':>8}{'mean_final_price':>20}{'mean_expected_revenue':>24}")
    for variant in sorted(summaries):
        s = summaries[variant]
        revenue_str = (
            f"{s.mean_expected_revenue:.2f}" if s.mean_expected_revenue is not None else "n/a"
        )
        print(f"{s.variant:<12}{s.decision_count:>8}{s.mean_final_price!s:>20}{revenue_str:>24}")


if __name__ == "__main__":
    main()
