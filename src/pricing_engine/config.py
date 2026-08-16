"""Flat constants for the serving layer (persistence + caching). No env-var
indirection or settings framework yet — add one only when a real deployment
target actually needs per-environment overrides.
"""

from __future__ import annotations

DB_PATH = "data/pricing_engine.db"
DB_URL = f"sqlite:///{DB_PATH}"

CACHE_TTL_SECONDS = 60
CACHE_MAXSIZE = 1024

SEED_DATA_DIR = "seed_data/catalog"
SEED_PRODUCTS_CSV = f"{SEED_DATA_DIR}/products.csv"
SEED_COMPETITOR_PRICES_CSV = f"{SEED_DATA_DIR}/competitor_prices.csv"

CATALOG_DB_PATH = "data/catalog.db"
CATALOG_DB_URL = f"sqlite:///{CATALOG_DB_PATH}"

ENABLE_ML_PRICING = False

SALES_HISTORY_PATH = "data/ml/sales_history.csv"
DEMAND_MODEL_PATH = "data/models/demand_model.joblib"

AB_TEST_EXPERIMENT_ID = "demand_elasticity_v1"
AB_TEST_TREATMENT_SPLIT = 0.5
