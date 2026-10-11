import json
from datetime import date

import pandas as pd

from app.core.validation import validate_dataset

START = date(2026, 10, 12)


def _counts(sample_dir) -> dict:
    return json.loads((sample_dir / "sample" / "row_counts.json").read_text())


def _copy(tables: dict) -> dict:
    return {name: frame.copy() for name, frame in tables.items()}


def _by_id(report: dict) -> dict:
    return {c["id"]: c for c in report["checks"]}


def test_all_six_pass_on_the_sample_data(tables, sample_dir):
    report = validate_dataset(tables, START, _counts(sample_dir))
    assert [c["id"] for c in report["checks"]] == ["V1", "V2", "V3", "V4", "V5", "V6"]
    assert report["ok"], report["checks"]
    assert report["units"]["duty_pct"].startswith("duty_pct: read as percent")


def test_dropping_one_transport_row_fails_v2(tables):
    broken = _copy(tables)
    lanes = broken["transport_duties"]
    broken["transport_duties"] = lanes[
        ~((lanes["plant"] == "C") & (lanes["destination"] == "Japan"))
    ]
    report = validate_dataset(broken, START)
    v2 = _by_id(report)["V2"]
    assert not v2["ok"] and not report["ok"]
    assert "C to Japan" in v2["detail"]


def test_an_order_for_an_unknown_product_fails_v1(tables):
    broken = _copy(tables)
    extra = pd.DataFrame(
        [{"order_id": "O-999", "product": "P9", "qty": 10, "destination": "UK", "due": START}]
    )
    broken["orders"] = pd.concat([broken["orders"], extra], ignore_index=True)
    v1 = _by_id(validate_dataset(broken, START))["V1"]
    assert not v1["ok"]
    assert "O-999" in v1["detail"]


def test_due_dates_on_or_before_the_start_fail_v4(tables):
    broken = _copy(tables)
    broken["orders"].loc[0, "due"] = START
    v4 = _by_id(validate_dataset(broken, START))["V4"]
    assert not v4["ok"]
    assert broken["orders"].loc[0, "order_id"] in v4["detail"]


def test_implausible_grid_carbon_fails_v5(tables):
    broken = _copy(tables)
    broken["plants"].loc[0, "carbon_kg_per_kwh"] = 3.5
    assert not _by_id(validate_dataset(broken, START))["V5"]["ok"]


def test_v6_compares_with_the_card_or_reports_counts(tables, sample_dir):
    expected = _counts(sample_dir) | {"orders": 151}
    v6 = _by_id(validate_dataset(tables, START, expected))["V6"]
    assert not v6["ok"]
    assert "orders 150 (card says 151)" in v6["detail"]

    no_card = _by_id(validate_dataset(tables, START, None))["V6"]
    assert no_card["ok"]
    assert no_card["detail"].startswith("no data card for this dataset, counts reported:")
