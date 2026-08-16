"""Pricing API: rules+guardrails engine, in-process TTL cache, SQLite audit log,
SQLite catalog store (populated via `python -m pricing_engine.ingestion.run`).
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from pricing_engine.api.dependencies import init_catalog_schema, init_db_schema
from pricing_engine.api.routes.pricing import router as pricing_router


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    init_db_schema()
    init_catalog_schema()
    yield


app = FastAPI(title="Dynamic Pricing Engine (scaffold)", lifespan=lifespan)
app.include_router(pricing_router)
