# Tests the independent plan checker catches broken plans.

import copy
from datetime import date

import pandas as pd
import pytest

from app.config import Settings
from app.core.plan_check import validate_plan
from app.core.solver import DEFAULT_WEIGHTS, solve_allocation

SETTINGS = Settings(_env_file=None)


def _tables() -> dict:
    orders = pd.DataFrame(
        [
            {
                "order_id": f"O-{i}",
                "product": p,
                "qty": 60,
                "destination": "UK",
                "due": date(2026, 10, 25),
            }
            for i, p in ((1, "P1"), (2, "P1"), (3, "P2"))
        ]
    )
    plants = pd.DataFrame(
        [
            {
                "plant": plant,
                "product": product,
                "weekly_capacity": 100,
                "unit_cost": cost,
                "energy_kwh_per_unit": 1.0,
                "carbon_kg_per_kwh": 0.5,
                "energy_price_per_kwh": 0.1,
                "week_start": None,
            }
            for plant, product, cost in (("A", "P1", 10.0), ("B", "P1", 12.0), ("A", "P2", 11.0))
        ]
    )
    lanes = pd.DataFrame(
        [
            {
                "plant": plant,
                "destination": "UK",
                "transport_cost_per_unit": 1.0,
                "transit_days": 2,
                "duty_pct": 0,
                "carbon_kg_per_unit": 0.1,
            }
            for plant in ("A", "B")
        ]
    )
    events = pd.DataFrame(
        columns=["event_id", "plant", "from_date", "to_date", "capacity_loss_pct"]
    )
    return {
        "orders": orders,
        "plants": plants,
        "transport_duties": lanes,
        "capacity_events": events,
    }


@pytest.fixture
def tiny():
    tables = _tables()
    return tables, solve_allocation(tables, SETTINGS, DEFAULT_WEIGHTS, solver="greedy")


def _all_ok(check: dict) -> bool:
    return all(v for k, v in check.items() if k.endswith("_ok"))


def test_valid_plan_passes(tiny):
    tables, plan = tiny
    check = validate_plan(plan, tables, SETTINGS)
    assert _all_ok(check), check["violations"]
    assert check["violations"] == []


def test_ineligible_plant_fails_eligibility(tiny):
    tables, plan = tiny
    bad = copy.deepcopy(plan)
    row = next(r for r in bad["rows"] if r["product"] == "P2")
    row["plant"] = "B"  # B does not make P2
    check = validate_plan(bad, tables, SETTINGS)
    assert not check["eligibility_ok"]


def test_overstuffed_week_fails_capacity(tiny):
    tables, plan = tiny
    bad = copy.deepcopy(plan)
    p1 = [r for r in bad["rows"] if r["product"] == "P1"]
    for row in p1:  # 60 + 60 > 100 in one plant-week
        row["plant"], row["week"] = "A", 0
    check = validate_plan(bad, tables, SETTINGS)
    assert not check["capacity_ok"]
    assert any(v.startswith("capacity: A P1 week 0") for v in check["violations"])


def test_flipped_on_time_flag_fails_delivery(tiny):
    tables, plan = tiny
    bad = copy.deepcopy(plan)
    bad["rows"][0]["on_time"] = not bad["rows"][0]["on_time"]
    assert not validate_plan(bad, tables, SETTINGS)["delivery_ok"]


def test_dropped_order_fails_completeness(tiny):
    tables, plan = tiny
    bad = copy.deepcopy(plan)
    bad["rows"] = bad["rows"][1:]
    assert not validate_plan(bad, tables, SETTINGS)["complete_ok"]


def test_tampered_cost_fails_numbers(tiny):
    tables, plan = tiny
    bad = copy.deepcopy(plan)
    bad["rows"][0]["cost"] += 5
    assert not validate_plan(bad, tables, SETTINGS)["numbers_ok"]


@pytest.mark.slow
def test_default_sample_plan_passes_every_check(tables):
    plan = solve_allocation(tables, SETTINGS, DEFAULT_WEIGHTS)
    check = validate_plan(plan, tables, SETTINGS)
    assert _all_ok(check), check["violations"]
