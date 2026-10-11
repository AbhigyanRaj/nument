# Database access: connects to SQLite, creates the tables,
# and reads the four data tables for the planning core.

"""Database access: a lazily created engine, sessions, and the table loader used by core.

The engine is created on first use from the current settings, so tests and the evaluation
can point DB_URL somewhere else and call `reset_engine()` without touching the demo database.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import date, datetime
from pathlib import Path

import pandas as pd
from sqlalchemy import event
from sqlalchemy.engine import Engine
from sqlmodel import Session, SQLModel, create_engine

from app import models  # noqa: F401  (registers the tables on SQLModel.metadata)
from app.config import get_settings

DATA_TABLES = ("orders", "plants", "transport_duties", "capacity_events")
DATE_COLUMNS = {
    "orders": ["due"],
    "plants": ["week_start"],
    "capacity_events": ["from_date", "to_date"],
}

_engine: Engine | None = None


def get_engine() -> Engine:
    global _engine
    if _engine is None:
        url = get_settings().db_url
        is_sqlite = url.startswith("sqlite")
        _engine = create_engine(url, connect_args={"check_same_thread": False} if is_sqlite else {})
        if is_sqlite:
            event.listen(_engine, "connect", _sqlite_pragmas)
    return _engine


def reset_engine() -> None:
    """Forget the current engine, e.g. after DB_URL changed. The next call creates a new one."""
    global _engine
    if _engine is not None:
        _engine.dispose()
    _engine = None


def _sqlite_pragmas(dbapi_connection, _record) -> None:
    # WAL lets the API read while an ingest or a plan is being written; the busy timeout makes
    # concurrent writers wait instead of failing with "database is locked".
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA busy_timeout=5000")
    cursor.execute("PRAGMA synchronous=NORMAL")
    cursor.close()


def init_db() -> None:
    url = get_settings().db_url
    if url.startswith("sqlite:///"):
        db_path = Path(url.removeprefix("sqlite:///"))
        db_path.parent.mkdir(parents=True, exist_ok=True)
    SQLModel.metadata.create_all(get_engine())


@contextmanager
def get_session() -> Iterator[Session]:
    with Session(get_engine()) as session:
        yield session


def load_tables() -> dict[str, pd.DataFrame]:
    """Read the four data tables. This is the only way app/core receives data."""
    tables: dict[str, pd.DataFrame] = {}
    with get_engine().connect() as conn:
        for name in DATA_TABLES:
            df = pd.read_sql_table(name, conn)
            df = df.drop(columns=["id"], errors="ignore")
            for column in DATE_COLUMNS.get(name, []):
                # Built as an object Series so missing dates stay None (map() would let
                # pandas re-infer datetime64 and turn them into NaT).
                df[column] = pd.Series(
                    [to_date(v) for v in df[column]], index=df.index, dtype=object
                )
            tables[name] = df
    return tables


def to_date(value) -> date | None:
    """Coerce a date-like value (date, datetime, Timestamp, ISO string, None/NaT) to a date."""
    if value is None:
        return None
    if isinstance(value, str):
        return date.fromisoformat(value[:10]) if value.strip() else None
    # Checked before the datetime branch: pandas' NaT is itself a datetime subclass.
    if pd.isna(value):
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return pd.Timestamp(value).date()
