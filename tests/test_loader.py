import json

import pandas as pd
from sqlmodel import select

from app.core.loader import ingest_csv
from app.db import get_session, load_tables
from app.models import IngestLog

ORDERS_HEADER = "order_id,product,qty,destination,due\n"


def _ingest(table: str, text: str, mode: str = "replace") -> dict:
    return ingest_csv(table, text.encode(), f"{table}.csv", mode)


def test_sample_tables_load_cleanly(tables):
    assert len(tables["orders"]) == 150
    assert len(tables["plants"]) == 15
    assert len(tables["transport_duties"]) == 36
    assert tables["capacity_events"].empty


def test_bad_rows_are_rejected_with_reasons(fresh_db):
    result = _ingest(
        "orders",
        ORDERS_HEADER
        + "O-1,P1,100,UK,2026-10-20\n"
        + "O-2,,100,UK,2026-10-20\n"
        + "O-3,P1,-5,UK,2026-10-20\n"
        + "O-4,P1,12.5,UK,2026-10-20\n"
        + "O-5,P1,abc,UK,2026-10-20\n"
        + "O-6,P1,10,UK,20/10/2026\n"
        + "O-1,P1,100,UK,2026-10-20\n",
    )
    assert result["status"] == "partial"
    assert result["rows_loaded"] == 1
    assert result["rows_rejected"] == 6
    reasons = {r["row"]: r["reason"] for r in result["rejects"]}
    assert reasons[3] == "product is blank"
    assert reasons[4].startswith("qty is negative")
    assert reasons[5].startswith("qty is not a whole number")
    assert reasons[6].startswith("qty is not a number")
    assert reasons[7].startswith("due is not a date")
    assert reasons[8] == "duplicate order_id=O-1 (first on row 2)"


def test_missing_columns_load_nothing(fresh_db):
    _ingest("orders", ORDERS_HEADER + "O-1,P1,100,UK,2026-10-20\n")
    result = _ingest("orders", "order_id,product\nO-9,P1\n")
    assert result["status"] == "error"
    assert result["missing_columns"] == ["qty", "destination", "due"]
    assert list(load_tables()["orders"]["order_id"]) == ["O-1"]


def test_extra_columns_are_ignored_and_reported(fresh_db):
    result = _ingest(
        "plants",
        "Plant, Product ,weekly_capacity,unit_cost,energy_kwh_per_unit,carbon_kg_per_kwh,colour\n"
        "Plant a,P1,100,20,4,0.8,blue\n",
    )
    assert result["status"] == "ok"
    assert result["ignored_columns"] == ["colour"]
    plants = load_tables()["plants"]
    assert plants.loc[0, "plant"] == "A"
    assert pd.isna(plants.loc[0, "energy_price_per_kwh"])


def test_append_upserts_by_key(fresh_db):
    header = "plant,destination,transport_cost_per_unit,transit_days,duty_pct,carbon_kg_per_unit\n"
    _ingest("transport_duties", header + "A,UK,4.0,14,4,2.0\nB,UK,1.5,3,0,0.4\n")
    result = _ingest("transport_duties", header + "A,UK,3.0,12,4,1.8\nC,UK,2.0,6,5,0.9\n", "append")
    assert result["status"] == "ok"
    lanes = load_tables()["transport_duties"].set_index(["plant", "destination"])
    assert len(lanes) == 3
    assert lanes.loc[("A", "UK"), "transit_days"] == 12


def test_header_only_file_clears_the_table(fresh_db):
    header = "event_id,plant,from_date,to_date,capacity_loss_pct\n"
    _ingest("capacity_events", header + "E-1,B,2026-10-19,2026-11-01,30\n")
    result = _ingest("capacity_events", header)
    assert result["status"] == "ok"
    assert load_tables()["capacity_events"].empty


def test_a_file_with_only_bad_rows_leaves_the_table_alone(fresh_db):
    header = "event_id,plant,from_date,to_date,capacity_loss_pct\n"
    _ingest("capacity_events", header + "E-1,B,2026-10-19,2026-11-01,30\n")
    result = _ingest(
        "capacity_events",
        header + "E-2,B,2026-11-01,2026-10-19,30\nE-3,B,2026-10-19,2026-11-01,140\n",
    )
    assert result["status"] == "error"
    assert [r["reason"] for r in result["rejects"]] == [
        "to_date is before from_date",
        "capacity_loss_pct must be between 0 and 100: 140",
    ]
    assert list(load_tables()["capacity_events"]["event_id"]) == ["E-1"]


def test_byte_order_mark_and_unknown_table(fresh_db):
    bom = "﻿" + ORDERS_HEADER + "O-1,P1,100,UK,2026-10-20\n"
    assert _ingest("orders", bom)["status"] == "ok"
    unknown = _ingest("widgets", ORDERS_HEADER)
    assert unknown["status"] == "error"
    assert unknown["errors"] == ["unknown table"]


def test_non_utf8_and_empty_files_are_errors(fresh_db):
    assert ingest_csv("orders", "é".encode("latin-1"), "x.csv")["errors"] == [
        "file is not UTF-8 text"
    ]
    assert ingest_csv("orders", b"", "x.csv")["errors"] == ["file is empty"]


def test_every_load_is_logged(fresh_db):
    _ingest("orders", ORDERS_HEADER + "O-1,P1,100,UK,2026-10-20\nO-2,P1,0,UK,2026-10-20\n")
    with get_session() as session:
        log = session.exec(select(IngestLog)).all()
    assert len(log) == 1
    assert log[0].status == "partial"
    assert json.loads(log[0].rejects_json)[0]["row"] == 3
