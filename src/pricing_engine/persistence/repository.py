"""Repository seam between the domain PriceDecision dataclass and the SQLAlchemy
ORM layer — mirrors how datasources/interfaces.py keeps the mock catalog
swappable. Callers never import SQLAlchemy directly.
"""

from __future__ import annotations

import json
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy.orm import Session, sessionmaker

from pricing_engine.persistence.models import PriceDecisionRecord
from pricing_engine.pricing.models import (
    GuardrailResult,
    PriceDecision,
    PricingContext,
    RuleAdjustment,
)


def _rule_adjustment_to_dict(a: RuleAdjustment) -> dict[str, Any]:
    return {
        "rule_name": a.rule_name,
        "adjustment_type": a.adjustment_type,
        "value": str(a.value),
        "reason": a.reason,
        "fired": a.fired,
    }


def _rule_adjustment_from_dict(d: dict[str, Any]) -> RuleAdjustment:
    return RuleAdjustment(
        rule_name=d["rule_name"],
        adjustment_type=d["adjustment_type"],
        value=Decimal(d["value"]),
        reason=d["reason"],
        fired=d["fired"],
    )


def _guardrail_result_to_dict(g: GuardrailResult) -> dict[str, Any]:
    return {
        "guardrail_name": g.guardrail_name,
        "passed": g.passed,
        "original_price": str(g.original_price),
        "adjusted_price": str(g.adjusted_price),
        "reason": g.reason,
    }


def _guardrail_result_from_dict(d: dict[str, Any]) -> GuardrailResult:
    return GuardrailResult(
        guardrail_name=d["guardrail_name"],
        passed=d["passed"],
        original_price=Decimal(d["original_price"]),
        adjusted_price=Decimal(d["adjusted_price"]),
        reason=d["reason"],
    )


def _context_to_dict(context: PricingContext) -> dict[str, Any]:
    return {
        "product_id": context.product_id,
        "base_price": str(context.base_price),
        "cost": str(context.cost),
        "inventory_level": context.inventory_level,
        "inventory_threshold_low": context.inventory_threshold_low,
        "competitor_prices": [str(p) for p in context.competitor_prices],
        "current_time": context.current_time.isoformat(),
        "metadata": context.metadata,
    }


def _context_from_dict(d: dict[str, Any]) -> PricingContext:
    return PricingContext(
        product_id=d["product_id"],
        base_price=Decimal(d["base_price"]),
        cost=Decimal(d["cost"]),
        inventory_level=d["inventory_level"],
        inventory_threshold_low=d["inventory_threshold_low"],
        competitor_prices=tuple(Decimal(p) for p in d["competitor_prices"]),
        current_time=datetime.fromisoformat(d["current_time"]),
        metadata=d["metadata"],
    )


def _record_to_decision(record: PriceDecisionRecord) -> PriceDecision:
    return PriceDecision(
        product_id=record.product_id,
        base_price=Decimal(record.base_price),
        final_price=Decimal(record.final_price),
        rule_adjustments=tuple(
            _rule_adjustment_from_dict(d) for d in json.loads(record.rule_adjustments_json)
        ),
        guardrail_results=tuple(
            _guardrail_result_from_dict(d) for d in json.loads(record.guardrail_results_json)
        ),
        decided_at=record.decided_at,
        context_snapshot=_context_from_dict(json.loads(record.context_snapshot_json)),
        variant=record.variant,
    )


class PriceDecisionRepository:
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def save(self, decision: PriceDecision) -> None:
        record = PriceDecisionRecord(
            product_id=decision.product_id,
            base_price=str(decision.base_price),
            final_price=str(decision.final_price),
            decided_at=decision.decided_at,
            variant=decision.variant,
            rule_adjustments_json=json.dumps(
                [_rule_adjustment_to_dict(a) for a in decision.rule_adjustments]
            ),
            guardrail_results_json=json.dumps(
                [_guardrail_result_to_dict(g) for g in decision.guardrail_results]
            ),
            context_snapshot_json=json.dumps(_context_to_dict(decision.context_snapshot)),
        )
        with self._session_factory() as session:
            session.add(record)
            session.commit()

    def find_by_product(
        self,
        product_id: str,
        since: datetime | None = None,
        until: datetime | None = None,
    ) -> list[PriceDecision]:
        with self._session_factory() as session:
            query = session.query(PriceDecisionRecord).filter(
                PriceDecisionRecord.product_id == product_id
            )
            if since is not None:
                query = query.filter(PriceDecisionRecord.decided_at >= since)
            if until is not None:
                query = query.filter(PriceDecisionRecord.decided_at <= until)
            records = query.order_by(PriceDecisionRecord.decided_at).all()
            return [_record_to_decision(r) for r in records]

    def find_all(
        self,
        since: datetime | None = None,
        until: datetime | None = None,
    ) -> list[PriceDecision]:
        with self._session_factory() as session:
            query = session.query(PriceDecisionRecord)
            if since is not None:
                query = query.filter(PriceDecisionRecord.decided_at >= since)
            if until is not None:
                query = query.filter(PriceDecisionRecord.decided_at <= until)
            records = query.order_by(PriceDecisionRecord.decided_at).all()
            return [_record_to_decision(r) for r in records]
