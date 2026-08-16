# Dynamic Pricing Engine — Progress

Full plan: [docs/dynamic-pricing-engine-plan_1.md](docs/dynamic-pricing-engine-plan_1.md)

## Current phase: Phases 1–5 (code) done; deploy/load-test and real vendor data deferred

### Done
- **Phase 2 — Rules Engine** (`src/pricing_engine/pricing/`)
  - `rules.py`: `InventoryBasedRule`, `TimeBasedRule`, `CompetitorBasedRule` — each independently evaluates a `PricingContext` and returns a multiplicative `RuleAdjustment`; never raises for "doesn't apply" (returns `fired=False`)
  - `guardrails.py`: `MinMaxGuardrail`, `MarginFloorGuardrail` — clamp price into bounds, never reject; clamping recorded as `passed=False` for audit
  - `engine.py`: `PricingEngine.decide_price()` orchestrates rules → guardrails → `PriceDecision`, giving a full auditable trail per decision
  - Unit tests in `tests/` cover rules/guardrails/engine
- **Phase 3 — Pricing API**: `GET /pricing/{product_id}` does cache-check → engine (on miss) → persist → cache → return.
  - **Caching**: `src/pricing_engine/caching/` — `DecisionCache` Protocol + `InMemoryTTLCache` (wraps `cachetools.TTLCache`, 60s default TTL, keyed by `product_id`). In-process, not Redis (none available in this environment) — but the Protocol seam makes a Redis-backed implementation a drop-in swap later.
  - **Audit-log persistence**: `src/pricing_engine/persistence/` — SQLite via SQLAlchemy (`db.py`, `models.py` ORM, `repository.py::PriceDecisionRepository`). Every genuinely computed decision is saved; cache hits are *not* re-persisted (audit trail = decisions made, not requests served).
  - Shared serializer: `pricing/serialization.py::decision_to_dict` (used by both the API response and, indirectly, persistence).
- **Phase 1 — Data ingestion** (CSV-based, since no real vendor/API/warehouse exists anywhere in this environment):
  - **Seed data**: `seed_data/catalog/products.csv` + `competitor_prices.csv` — 10 synthetic products (committed, NOT gitignored, unlike `data/`).
  - **Catalog store**: `src/pricing_engine/catalog/` — separate SQLite DB (`data/catalog.db`) from the Phase 3 audit log, its own `CatalogBase`, `products`/`competitor_prices` tables, `CatalogRepository` (`upsert_product` via `session.merge`, `replace_competitor_prices` via delete-then-insert — both idempotent).
  - **Ingestion pipeline**: `src/pricing_engine/ingestion/seed_loader.py::run_ingestion()` reads the CSVs and upserts into the catalog. Run manually via `python -m pricing_engine.ingestion.run` — deliberately NOT auto-run in the API's `lifespan` (only schema creation is); loading data is a batch job with its own cadence, decoupled from web-process uptime.
  - **Real datasources**: `src/pricing_engine/datasources/sqlite.py::SqliteProductDataSource`/`SqliteCompetitorPriceSource` — finally exercise the `ProductDataSource`/`CompetitorPriceSource` Protocol split (previously defined but unused). This is what the live app uses now; `datasources/mock.py` stays as a test-only fixture (see its docstring).
- **Wiring**: `src/pricing_engine/api/dependencies.py` holds all module singletons (catalog + audit-log DBs, engine, cache) behind FastAPI `Depends`; tests override them via `app.dependency_overrides`. `api/main.py`'s `lifespan` creates both SQLite schemas on startup (catalog schema only — not data; run ingestion separately to populate it).
- **Phase 4 — Statistical/ML model** (airline demand/elasticity, feature-flagged, `src/pricing_engine/ml/`):
  - **Domain**: the existing generic `sku-1..sku-10` catalog is untouched; 5 flight-route products were added alongside them (`flight-jfk-lax-2026-10-15` etc.), using `catalog/models.py`'s new nullable `route`/`departure_date` columns. `SqliteProductDataSource` populates `context.metadata` (`route`, `days_to_departure`) only for these — generic products keep `metadata={}` exactly as before.
  - **Synthetic historical sales**: `ml/generate_sales_history.py` simulates a daily booking curve per (route, flight) over 120 days pre-departure — a continuous scarcity+urgency ground-truth price formula (cousin of `InventoryBasedRule`/`TimeBasedRule`) drives simulated passenger willingness-to-pay against that price, so price↑ → bookings↓ is a genuine, learnable relationship, not noise. Seeded/deterministic; ~12k rows written to `data/ml/sales_history.csv` (gitignored) via `python -m pricing_engine.ml.generate_sales_history`.
  - **Model**: `ml/features.py` (day_of_week/is_last_minute/load_factor/price_per_seat_remaining) → `ml/train.py` trains a `HistGradientBoostingRegressor` (monotonic-constrained on price, so demand is guaranteed non-increasing in price — an unconstrained model empirically predicted demand *rising* with price in some regions) predicting daily bookings, evaluated on a **chronological** holdout split (last 20% of departures per route), gated on beating a naive mean baseline by ≥20% MAE (achieves ~36% in practice) before saving to `data/models/demand_model.joblib` (gitignored). Run via `python -m pricing_engine.ml.train`.
  - **Integration**: `ml/model.py::DemandModel.predict_elasticity()` derives elasticity via finite-difference price perturbation (10%, not 1% — tree models are piecewise-constant, a 1% nudge often doesn't cross a split boundary and yields a false zero). `ml/rule.py::DemandElasticityRule` implements the existing `PricingRule` ABC unchanged — no-ops (`fired=False`) for generic products or a missing model file, otherwise maps elasticity to a bounded `[0.85, 1.15]` multiplier.
  - **Feature flag**: `config.ENABLE_ML_PRICING` (default `False`). `api/dependencies.py` appends `DemandElasticityRule` to the rules list only if the flag is on *and* the model file exists, via a local (not top-of-file) import — keeps sklearn/pandas/joblib off the API's import path entirely when the flag is off.
  - **Backtest**: `ml/backtest.py::run_backtest()` compares rules-only vs. rules+ML pricing over held-out rows — explicitly documented as a circular sanity check (same model prices and evaluates), not an independent validation; a real backtest needs real held-out outcomes, which don't exist for synthetic data by construction.
  - Manually verified end-to-end: generated data → trained model (beat baseline) → flipped the flag → `curl` a flight product (rule fired, plausible elasticity in the audit trail) → `curl sku-1` (rule no-opped, unchanged from pre-Phase-4 behavior).
- **Phase 5 — Experimentation (A/B testing)** (`src/pricing_engine/experimentation/`), turning `ENABLE_ML_PRICING` from a blunt deployment-wide switch into a real sticky experiment:
  - **Assignment**: `experimentation/assignment.py::assign_variant(customer_id, experiment_id, treatment_split)` — deterministic `sha256(experiment_id:customer_id)` hash bucketed into `"control"`/`"treatment"`, no stored assignment table (the hash *is* the table). `is_experiment_active()` reuses the same `ENABLE_ML_PRICING and os.path.exists(DEMAND_MODEL_PATH)` gate `api/dependencies.py` already used pre-Phase-5.
  - **Two engines**: `api/dependencies.py` builds `_control_engine` (rules-only) and `_treatment_engine` (rules + `DemandElasticityRule`, when the model exists) from **copies** of the same base rules list — sharing one list and mutating it would've silently coupled the two engines' rule sets. `get_pricing_engine()` was renamed to `get_control_engine()`.
  - **Route**: `GET /pricing/{product_id}?customer_id=...` (defaults to `"anonymous"` — a fixed string, not a per-request random id, so caching/assignment stay deterministic for anonymous traffic). When the experiment is inactive (default), every request is forced to `"control"` regardless of `customer_id` — zero behavior change from pre-Phase-5. Cache key became `f"{product_id}:{variant}"` so a treatment-priced decision can never leak to a control-assigned customer.
  - **Audit trail**: `PriceDecision`/`PriceDecisionRecord` gained a `variant: str = "control"` field/column (default protects every pre-existing construction site); the route tags it via `dataclasses.replace()` after `decide_price()` returns — the engine itself still knows nothing about experiments.
  - **Metrics**: `experimentation/metrics.py::summarize_by_variant()` + `python -m pricing_engine.experimentation.metrics` CLI — per-variant `mean_final_price` and a `DemandModel`-estimated `mean_expected_revenue` (flight-product decisions only, `None` otherwise). Explicitly a synthetic proxy, not real revenue — this system has no conversion/purchase event to measure against. Not a dashboard (Phase 6 territory).
  - Manually verified end-to-end: flag off → unchanged default behavior; flag on → two customers hashed to different variants got different prices for the same flight product, a third call with the first customer's id was served from cache (identical `decided_at`), and the metrics CLI printed both variants with sane counts/prices.
- Tests: `tests/persistence/`, `tests/caching/`, `tests/catalog/`, `tests/ingestion/`, `tests/datasources/`, `tests/ml/`, `tests/experimentation/`, extended `tests/api/test_pricing_endpoint.py`. 106 tests passing (one marked `slow`, not excluded by default — trains a real small model in ~2s); `ruff check .` and `mypy src` clean.

### Not started
- **Real vendor/warehouse ingestion**: no such source exists to connect to; the CSV-reader-behind-a-Protocol seam is what makes swapping one in later a small change.
- **Phase 3 remainder (deferred, needs real infra)**: real Redis (currently in-process TTL cache), Postgres (currently SQLite), staging deploy, load test — `infra/` is still just a placeholder, no Docker/CI in this repo
- **Real historical booking data / a non-circular backtest**: the Phase 4 simulation is a stand-in, same spirit as Phase 1's CSV-instead-of-vendor-feed choice; flagged as a known limitation in `ml/backtest.py`
- **A real conversion/revenue metric**: `experimentation/metrics.py`'s `mean_expected_revenue` is a `DemandModel`-estimated proxy, not a measured outcome — flagged as a known limitation
- **Phase 6 — Monitoring & guardrail alerting**
- **Phase 7 — Rollout**

### Next step
Phases 1–5 are "done for a scaffold." Phase 6/7 both need real infra (metrics/alerting stack, deployment target) that doesn't exist in this environment — realistically, stop here until real data sources / deployment infra are actually available, or revisit once there's a real conversion event to replace the synthetic revenue proxy in Phase 5's metrics.

### Note on Python version
This machine only has Python 3.9.6 (no 3.11 available). `pyproject.toml`
(`requires-python`, `ruff` target, `mypy` python_version) is pinned to 3.9, not the
3.11+ the original plan doc assumed. All modules use `from __future__ import
annotations`, so modern generic syntax (`list[X]`, `X | None`) still works at runtime.
Don't "fix" this back to 3.11 unless a newer interpreter is actually available.

## Commands
```bash
pip install -e ".[dev]"
pytest
ruff check .
mypy src
python -m pricing_engine.ingestion.run              # seed the catalog DB (run before/alongside the API)
python -m pricing_engine.ml.generate_sales_history   # regenerate synthetic sales history (Phase 4)
python -m pricing_engine.ml.train                    # train + save the demand model (Phase 4)
uvicorn pricing_engine.api.main:app --reload   # then: curl localhost:8000/pricing/sku-1
# set config.ENABLE_ML_PRICING = True (after training) to activate the A/B test, e.g.:
# curl 'localhost:8000/pricing/flight-jfk-lax-2026-10-15?customer_id=customer-0'
python -m pricing_engine.experimentation.metrics   # per-variant report (needs ENABLE_ML_PRICING having been on for some logged decisions)
```
