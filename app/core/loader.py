# Loads CSV files into the database, checking every row.
# Bad rows are rejected with a clear reason; good rows are saved.

"""CSV ingestion: read a file, clean and check every row, then write the valid rows.

Every load is recorded in the ingest log, including failed ones. A file whose rows are all
rejected never touches the table, so a bad upload cannot wipe good data.
"""

from __future__ import annotations

import io
import json
import math
import re
from collections.abc import Callable
from datetime import date, datetime

import pandas as pd
from sqlalchemy import delete

from app.db import get_session
from app.models import CapacityEvent, IngestLog, Order, Plant, TransportDuty

REQUIRED: dict[str, list[str]] = {
    "orders": ["order_id", "product", "qty", "destination", "due"],
    "plants": [
        "plant",
        "product",
        "weekly_capacity",
        "unit_cost",
        "energy_kwh_per_unit",
        "carbon_kg_per_kwh",
    ],
    "transport_duties": [
        "plant",
        "destination",
        "transport_cost_per_unit",
        "transit_days",
        "duty_pct",
        "carbon_kg_per_unit",
    ],
    "capacity_events": ["event_id", "plant", "from_date", "to_date", "capacity_loss_pct"],
}
# Optional columns the model understands; any other extra column is ignored and reported.
OPTIONAL: dict[str, list[str]] = {"plants": ["energy_price_per_kwh", "week_start"]}
KEYS: dict[str, tuple[str, ...]] = {
    "orders": ("order_id",),
    "plants": ("plant", "product", "week_start"),
    "transport_duties": ("plant", "destination"),
    "capacity_events": ("event_id",),
}
MODELS = {
    "orders": Order,
    "plants": Plant,
    "transport_duties": TransportDuty,
    "capacity_events": CapacityEvent,
}
MAX_ROWS = 100_000
REJECTS_RETURNED = 20
REJECTS_LOGGED = 200


class RowError(ValueError):
    """A row-level problem; the message is shown to the user as the reject reason."""


# --- Field parsers ---------------------------------------------------------------------------


def _text(raw: str, column: str) -> str:
    value = raw.strip()
    if not value:
        raise RowError(f"{column} is blank")
    return value


def _plant(raw: str, column: str) -> str:
    # "Plant A", "plant_a" and " a " all mean plant A.
    value = re.sub(r"^PLANT[\s_-]*", "", _text(raw, column).upper())
    if not value:
        raise RowError(f"{column} is blank")
    return value


def _number(raw: str, column: str) -> float:
    value = _text(raw, column)
    try:
        number = float(value)
    except ValueError:
        raise RowError(f"{column} is not a number: {value!r}") from None
    if not math.isfinite(number):
        raise RowError(f"{column} is not a finite number: {value!r}")
    if number < 0:
        raise RowError(f"{column} is negative: {value}")
    return number


def _whole(raw: str, column: str, *, positive: bool) -> int:
    number = _number(raw, column)
    if number != int(number):
        raise RowError(f"{column} is not a whole number: {raw.strip()}")
    if positive and number <= 0:
        raise RowError(f"{column} must be a positive whole number: {raw.strip()}")
    return int(number)


def _date(raw: str, column: str) -> date:
    value = _text(raw, column)
    for candidate in (value, value.replace("/", "-")):
        try:
            return datetime.fromisoformat(candidate).date()
        except ValueError:
            continue
    raise RowError(f"{column} is not a date (use YYYY-MM-DD): {value!r}")


def _optional_number(raw: str, column: str) -> float | None:
    return _number(raw, column) if raw.strip() else None


def _optional_date(raw: str, column: str) -> date | None:
    return _date(raw, column) if raw.strip() else None


# --- Row parsers ----------------------------------------------------------------------------


def _order(row: dict[str, str]) -> dict:
    return {
        "order_id": _text(row["order_id"], "order_id"),
        "product": _text(row["product"], "product"),
        "qty": _whole(row["qty"], "qty", positive=True),
        "destination": _text(row["destination"], "destination"),
        "due": _date(row["due"], "due"),
    }


def _plant_row(row: dict[str, str]) -> dict:
    return {
        "plant": _plant(row["plant"], "plant"),
        "product": _text(row["product"], "product"),
        "weekly_capacity": _whole(row["weekly_capacity"], "weekly_capacity", positive=True),
        "unit_cost": _number(row["unit_cost"], "unit_cost"),
        "energy_kwh_per_unit": _number(row["energy_kwh_per_unit"], "energy_kwh_per_unit"),
        "carbon_kg_per_kwh": _number(row["carbon_kg_per_kwh"], "carbon_kg_per_kwh"),
        "energy_price_per_kwh": _optional_number(
            row.get("energy_price_per_kwh", ""), "energy_price_per_kwh"
        ),
        "week_start": _optional_date(row.get("week_start", ""), "week_start"),
    }


def _transport(row: dict[str, str]) -> dict:
    return {
        "plant": _plant(row["plant"], "plant"),
        "destination": _text(row["destination"], "destination"),
        "transport_cost_per_unit": _number(
            row["transport_cost_per_unit"], "transport_cost_per_unit"
        ),
        "transit_days": _whole(row["transit_days"], "transit_days", positive=False),
        "duty_pct": _number(row["duty_pct"], "duty_pct"),
        "carbon_kg_per_unit": _number(row["carbon_kg_per_unit"], "carbon_kg_per_unit"),
    }


def _event(row: dict[str, str]) -> dict:
    parsed = {
        "event_id": _text(row["event_id"], "event_id"),
        "plant": _plant(row["plant"], "plant"),
        "from_date": _date(row["from_date"], "from_date"),
        "to_date": _date(row["to_date"], "to_date"),
        "capacity_loss_pct": _number(row["capacity_loss_pct"], "capacity_loss_pct"),
    }
    if parsed["to_date"] < parsed["from_date"]:
        raise RowError("to_date is before from_date")
    if parsed["capacity_loss_pct"] > 100:
        raise RowError(f"capacity_loss_pct must be between 0 and 100: {row['capacity_loss_pct']}")
    return parsed


PARSERS: dict[str, Callable[[dict[str, str]], dict]] = {
    "orders": _order,
    "plants": _plant_row,
    "transport_duties": _transport,
    "capacity_events": _event,
}


# --- Ingestion ------------------------------------------------------------------------------


def _normalise_header(name: object) -> str:
    return re.sub(r"[\s-]+", "_", str(name).strip().lower())


def _read(file_bytes: bytes) -> pd.DataFrame:
    if not file_bytes.strip():
        raise ValueError("file is empty")
    try:
        text = file_bytes.decode("utf-8-sig")  # also strips a byte-order mark
    except UnicodeDecodeError:
        raise ValueError("file is not UTF-8 text") from None
    try:
        frame = pd.read_csv(io.StringIO(text), dtype=str, keep_default_na=False)
    except (pd.errors.ParserError, pd.errors.EmptyDataError) as exc:
        raise ValueError(f"could not read the CSV: {exc}") from None
    frame.columns = [_normalise_header(c) for c in frame.columns]
    return frame


def _describe_key(table: str, key: tuple) -> str:
    return ", ".join(f"{k}={v}" for k, v in zip(KEYS[table], key, strict=True))


def ingest_csv(table: str, file_bytes: bytes, filename: str, mode: str = "replace") -> dict:
    """Load one CSV into `table`. Row numbers in rejects are file line numbers (header = 1)."""
    result: dict = {
        "table": table,
        "rows_loaded": 0,
        "rows_rejected": 0,
        "rejects": [],
        "ignored_columns": [],
        "status": "error",
        "errors": [],
    }
    if table not in REQUIRED:
        result["errors"] = ["unknown table"]
        _log(table, filename, result, [])
        return result
    if mode not in ("replace", "append"):
        result["errors"] = ["mode must be 'replace' or 'append'"]
        _log(table, filename, result, [])
        return result

    try:
        frame = _read(file_bytes)
    except ValueError as exc:
        result["errors"] = [str(exc)]
        _log(table, filename, result, [])
        return result

    missing = [c for c in REQUIRED[table] if c not in frame.columns]
    if missing:
        result["missing_columns"] = missing
        result["errors"] = [f"missing required columns: {', '.join(missing)}"]
        _log(table, filename, result, [])
        return result
    if len(frame) > MAX_ROWS:
        result["errors"] = [f"file has more than {MAX_ROWS:,} rows"]
        _log(table, filename, result, [])
        return result

    known = set(REQUIRED[table]) | set(OPTIONAL.get(table, []))
    result["ignored_columns"] = [c for c in frame.columns if c not in known]

    rows: list[dict] = []
    rejects: list[dict] = []
    first_seen: dict[tuple, int] = {}
    for line, raw in enumerate(frame.to_dict("records"), start=2):
        try:
            parsed = PARSERS[table](raw)
        except RowError as exc:
            rejects.append({"row": line, "reason": str(exc)})
            continue
        key = tuple(parsed[k] for k in KEYS[table])
        if key in first_seen:
            rejects.append(
                {
                    "row": line,
                    "reason": f"duplicate {_describe_key(table, key)} (first on row {first_seen[key]})",
                }
            )
            continue
        first_seen[key] = line
        rows.append(parsed)

    loaded, rejected = len(rows), len(rejects)
    if rejected == 0:
        status = "ok"
    elif loaded:
        status = "partial"
    else:
        status = "error"
    if status != "error":
        _write(table, rows, mode)

    result.update(
        rows_loaded=loaded if status != "error" else 0,
        rows_rejected=rejected,
        rejects=rejects[:REJECTS_RETURNED],
        status=status,
    )
    if status == "error":
        result["errors"] = ["every row was rejected; the table was left unchanged"]
    _log(table, filename, result, rejects)
    return result


def _write(table: str, rows: list[dict], mode: str) -> None:
    model = MODELS[table]
    with get_session() as session:
        if mode == "replace":
            session.execute(delete(model))
            session.add_all([model(**row) for row in rows])
        else:  # append = upsert by natural key
            for row in rows:
                session.execute(
                    delete(model).where(*(getattr(model, k) == row[k] for k in KEYS[table]))
                )
                session.add(model(**row))
        session.commit()


def _log(table: str, filename: str, result: dict, rejects: list[dict]) -> None:
    with get_session() as session:
        session.add(
            IngestLog(
                table_name=table,
                filename=filename,
                rows_loaded=result["rows_loaded"],
                rows_rejected=result["rows_rejected"],
                rejects_json=json.dumps(rejects[:REJECTS_LOGGED] or result["errors"]),
                status=result["status"],
            )
        )
        session.commit()
