"""SQLAlchemy engine/session setup for the audit-log store.

SQLite has a single-writer lock — fine for this scaffold's request volume, but
a real deployment with concurrent writers would need WAL mode or a queue.
"""

from __future__ import annotations

import os

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from pricing_engine.config import DB_URL
from pricing_engine.persistence.models import Base


def make_engine(db_url: str = DB_URL) -> Engine:
    if not db_url.startswith("sqlite"):
        return create_engine(db_url)
    if db_url.endswith(":memory:"):
        # A plain in-memory sqlite engine hands out a fresh empty DB per
        # connection; StaticPool pins it to a single shared connection so
        # init_db() and later reads/writes see the same database.
        return create_engine(
            db_url,
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
    return create_engine(db_url, connect_args={"check_same_thread": False})


def make_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, expire_on_commit=False)


def init_db(engine: Engine) -> None:
    db_path = engine.url.database
    if engine.url.get_backend_name() == "sqlite" and db_path and db_path != ":memory:":
        db_dir = os.path.dirname(db_path)
        if db_dir:
            os.makedirs(db_dir, exist_ok=True)
    Base.metadata.create_all(engine)
