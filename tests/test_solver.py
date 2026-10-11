# Tests the solver: valid plans, on-time choices, weights and capacity loss.

from datetime import date

import pandas as pd
import pytest

from app.config import Settings
from app.core import solver as solver_module
from app.core.solver import (
    DEFAULT_WEIGHTS,
    objective_value,
    plan_context,
    run_solver,
    solve_allocation,
)

SETTINGS = Settings(_env_file=None)


def _tiny_tables() -> dict:
    orders = pd.DataFrame(
        [
            {
                "order_id": "O-1",
                "product": "P1",
                "qty": 80,
                "destination": "UK",
                "due": date(2026, 10, 25),
            },
            {
                "order_id": "O-2",
                "product": "P1",
                "qty": 80,
                "destination": "UK",
                "due": date(2026, 10, 25),
            },
        ]
    )
    plants = pd.DataFrame(
        [
            {
                "plant": p,
                "product": "P1",
                "weekly_capacity": 100,
                "unit_cost": c,
                "energy_kwh_per_unit": 1.0,
                "carbon_kg_per_kwh": 0.5,
                "energy_price_per_kwh": 0.1,
                "week_start": None,
            }
            for p, c in (("A", 10.0), ("B", 12.0))
        ]
    )
    lanes = pd.DataFrame(
        [
            {
                "plant": p,
                "destination": "UK",
                "transport_cost_per_unit": 1.0,
                "transit_days": 2,
                "duty_pct": 0,
                "carbon_kg_per_unit": 0.1,
            }
            for p in ("A", "B")
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


def _respects_capacity(plan: dict) -> bool:
    return all(c["used"] <= c["effective"] for c in plan["capacity"])


def test_tiny_case_assigns_both_orders_within_capacity():
    tables = _tiny_tables()
    tables["plants"]["weekly_capacity"] = 100
    plan = solve_allocation(tables, SETTINGS, DEFAULT_WEIGHTS, {"only_orders": ["O-1", "O-2"]})
    assert plan["unmet"] == []
    assert len(plan["rows"]) == 2  # 80 + 80 > 100: never both in one plant-week
    assert _respects_capacity(plan)


def test_greedy_fallback_when_cpsat_fails(monkeypatch):
    def boom(*_args, **_kwargs):
        raise RuntimeError("solver crashed")

    monkeypatch.setattr(solver_module, "solve_cpsat", boom)
    plan = solve_allocation(_tiny_tables(), SETTINGS, DEFAULT_WEIGHTS)
    assert plan["solver"] == "greedy" and plan["fallback"] is True
    assert len(plan["rows"]) == 2


@pytest.fixture(scope="module")
def default_plan(tables):
    return solve_allocation(tables, SETTINGS, DEFAULT_WEIGHTS)


@pytest.mark.slow
def test_o077_is_on_time_under_default_weights(default_plan):
    row = next(r for r in default_plan["rows"] if r["order_id"] == "O-077")
    assert row["on_time"] and row["plant"] != "A"
    assert _respects_capacity(default_plan)
    assert default_plan["kpis"]["unmet_orders"] == 0


@pytest.mark.slow
def test_cost_first_is_cheaper_and_carbon_first_is_greener(tables):
    cost_first = solve_allocation(tables, SETTINGS, {"cost": 1, "carbon": 0, "lateness": 1})["kpis"]
    carbon_first = solve_allocation(tables, SETTINGS, {"cost": 0, "carbon": 1, "lateness": 1})[
        "kpis"
    ]
    # Plans are proven within a small optimality gap, so allow 1% of slack.
    assert cost_first["total_cost"] <= carbon_first["total_cost"] * 1.01
    assert carbon_first["total_carbon_t"] <= cost_first["total_carbon_t"] * 1.01


@pytest.mark.slow
def test_cpsat_is_never_worse_than_greedy(tables):
    ctx = plan_context(tables, SETTINGS)
    exact = run_solver(ctx, SETTINGS, DEFAULT_WEIGHTS)
    greedy = run_solver(ctx, SETTINGS, DEFAULT_WEIGHTS, solver="greedy")
    assert objective_value(ctx.options, exact, DEFAULT_WEIGHTS) <= objective_value(
        ctx.options, greedy, DEFAULT_WEIGHTS
    )


@pytest.mark.slow
def test_severe_event_leaves_orders_unmet_but_respects_capacity(tables, sample_dir):
    severe = pd.read_csv(sample_dir / "drop" / "capacity_events_severe.csv")
    severe["from_date"] = pd.to_datetime(severe["from_date"]).dt.date
    severe["to_date"] = pd.to_datetime(severe["to_date"]).dt.date
    plan = solve_allocation({**tables, "capacity_events": severe}, SETTINGS, DEFAULT_WEIGHTS)
    assert plan["unmet"]
    assert all(oid.startswith("O-") for oid in plan["unmet"])
    assert _respects_capacity(plan)
