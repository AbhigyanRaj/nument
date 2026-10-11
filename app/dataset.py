"""Dataset-level helpers shared by the CLIs and the API: which data card applies to the data
in the database, and the validation report for it."""

from __future__ import annotations

import json
from pathlib import Path

from sqlmodel import select

from app.config import get_settings
from app.core.calendar import planning_start
from app.core.validation import validate_dataset
from app.db import get_session, load_tables
from app.models import IngestLog

CARD_NAME = "row_counts.json"


def _latest_loads() -> dict[str, str]:
    """Table -> file name of its latest successful load."""
    with get_session() as session:
        logs = session.exec(
            select(IngestLog).where(IngestLog.status != "error").order_by(IngestLog.id)
        ).all()
    return {log.table_name: log.filename for log in logs}


def expected_counts() -> dict[str, int] | None:
    """Row counts from the data card next to the files the data came from.

    The card is the row_counts.json in the folder of the latest orders load, and only tables
    whose latest load came from that same folder are compared (a late event drop changes the
    events table on purpose). Uploads are stored without a folder, so they have no card."""
    latest = _latest_loads()
    orders_file = latest.get("orders")
    if not orders_file or not Path(orders_file).is_absolute():
        return None
    folder = Path(orders_file).parent
    card = folder / CARD_NAME
    if not card.is_file():
        return None
    counts = json.loads(card.read_text(encoding="utf-8"))
    return {
        table: n
        for table, n in counts.items()
        if table in latest and Path(latest[table]).parent == folder
    }


def validation_report() -> dict:
    tables = load_tables()
    start = planning_start(tables["orders"], get_settings())
    return validate_dataset(tables, start, expected_counts())
