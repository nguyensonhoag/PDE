# Dynamic Pricing Engine

Rules-based pricing engine with guardrails and a full audit trail per price decision.

See `docs/dynamic-pricing-engine-plan_1.md` for the full project plan. This repo currently
implements Phase 2 (rules engine + guardrails) plus a thin, placeholder read-only API stub.
Ingestion, ML, experimentation, monitoring, and deployment are not yet built — see the plan
doc for open questions blocking those phases.

## Setup

```bash
pip install -e ".[dev]"
```

## Test

```bash
pytest
ruff check .
mypy src
```

## Run the API stub

```bash
uvicorn pricing_engine.api.main:app --reload
curl localhost:8000/pricing/sku-1
```

The API is backed by an in-memory mock catalog (`pricing_engine/datasources/mock.py`) —
not real ingestion. Swap in a real `ProductDataSource`/`CompetitorPriceSource` implementation
when Phase 1 ingestion exists.
