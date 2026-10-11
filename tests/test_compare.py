import pytest

from app.config import Settings
from app.core.compare import (
    baseline_cheapest_plan,
    compare_plans,
    explain_order,
    recommendations,
    tradeoff_table,
)
from app.core.solver import DEFAULT_WEIGHTS, solve_allocation

SETTINGS = Settings(_env_file=None)


def _row(oid, plant, cost, carbon, days_late=0):
    return {
        "order_id": oid,
        "plant": plant,
        "cost": cost,
        "carbon_kg": carbon,
        "days_late": days_late,
    }


def _plan(rows, unmet=()):
    return {
        "rows": rows,
        "unmet": list(unmet),
        "status": "OPTIMAL",
        "kpis": {
            "total_cost": sum(r["cost"] for r in rows),
            "total_carbon_t": sum(r["carbon_kg"] for r in rows) / 1000,
            "late_orders": sum(1 for r in rows if r["days_late"]),
            "unmet_orders": len(unmet),
        },
    }


def test_compare_plans_on_a_hand_built_pair():
    base = _plan([_row("O-1", "B", 100, 50), _row("O-2", "B", 200, 80), _row("O-3", "A", 50, 90)])
    new = _plan([_row("O-1", "C", 130, 20), _row("O-2", "B", 200, 80)], unmet=["O-3"])
    cmp = compare_plans(base, new)
    assert cmp["moved_count"] == 2
    assert cmp["extra_cost"] == -20
    assert cmp["unmet_change"] == 1
    assert cmp["stability_pct"] == pytest.approx(33.3)
    assert cmp["moved"][0] == {
        "order_id": "O-1",
        "from_plant": "B",
        "to_plant": "C",
        "cost_change": 30,
        "carbon_change_kg": -30,
        "became_late": False,
    }
    o1 = new["rows"][0]
    assert o1["moved"] is True and o1["base_plant"] == "B"
    assert new["rows"][1]["moved"] is False


def test_unknown_order_is_not_found(tables):
    assert explain_order("O-999", {"rows": [], "unmet": []}, tables, SETTINGS) == {
        "found": False,
        "order_id": "O-999",
    }


@pytest.fixture(scope="module")
def default_plan(tables):
    return solve_allocation(tables, SETTINGS, DEFAULT_WEIGHTS)


@pytest.mark.slow
def test_o077_explanation(default_plan, tables):
    exp = explain_order("O-077", default_plan, tables, SETTINGS)
    assert exp["found"] and exp["chosen_plant"] != "A"
    codes = {c["code"] for c in exp["reason_codes"]}
    assert "CHEAPEST_OPTION_LATE" in codes
    a = next(r for r in exp["rows"] if r["plant"] == "A")
    assert a["days_late"] == 3 and not a["on_time"] and not a["chosen"]
    assert sum(r["chosen"] for r in exp["rows"]) == 1


@pytest.mark.slow
def test_single_plant_order_reports_only_eligible_plant(default_plan, tables):
    p4 = tables["orders"].loc[tables["orders"]["product"] == "P4", "order_id"].iloc[0]
    codes = {c["code"] for c in explain_order(p4, default_plan, tables, SETTINGS)["reason_codes"]}
    assert "ONLY_ELIGIBLE_PLANT" in codes


@pytest.mark.slow
def test_tradeoff_10_is_feasible_and_60_is_not(tables):
    rows = {
        r["carbon_cut_pct"]: r
        for r in tradeoff_table(tables, SETTINGS, DEFAULT_WEIGHTS, cuts=(0, 10, 60))
    }
    assert rows[10]["feasible"] and rows[10]["cost"] >= rows[0]["cost"]
    assert rows[10]["carbon_t"] < rows[0]["carbon_t"]
    assert not rows[60]["feasible"]


@pytest.mark.slow
def test_baseline_ignores_dates_and_is_late_more_often(default_plan, tables):
    baseline = baseline_cheapest_plan(tables, SETTINGS)
    assert baseline["solver"] == "greedy"
    assert baseline["kpis"]["late_orders"] > default_plan["kpis"]["late_orders"]


def test_recommendations_from_facts():
    base = _plan([_row("O-1", "B", 100, 50)])
    new = _plan([_row("O-1", "C", 130, 20, days_late=2)])
    cmp = compare_plans(base, new)
    items = recommendations(new, cmp, check={"capacity_ok": True, "eligibility_ok": True})
    assert items[0]["action"] == "Approve re-plan: move 1 orders off Plant B"
    assert items[0]["estimated_impact"]["cost"] == 30
    assert items[0]["requires_approval"] and items[0]["confidence"] == "high"
    assert any(i["action"].startswith("Tell customers about 1 late") for i in items)
    assert recommendations(new, cmp, check={"capacity_ok": False})[0]["confidence"] == "medium"
