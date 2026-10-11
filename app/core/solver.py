"""Allocation solvers: exact CP-SAT, and a greedy heuristic used as baseline and fallback.

Both minimise the same objective. Cost and carbon are divided by reference totals (the
cheapest and the greenest option of every order) so both become unitless and the weights
mean what they say. A late order adds `lateness` (1.0 by default, the size of the whole
cost-plus-carbon term) plus 1% per day late, so a delivery date is never traded for money
unless the user lowers the lateness weight. An order left unmet costs 100.
"""

from __future__ import annotations

import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, timedelta

import pandas as pd
from ortools.sat.python import cp_model

from app.core.calendar import (
    base_capacity,
    effective_capacity,
    horizon_weeks,
    normalise_pct,
    pct_scale,
    planning_start,
    to_fraction,
    week_start,
)
from app.core.costing import Option, build_options, cheapest_option_per_order
from app.core.scenario import normalise_scenario, scenario_json

SCALE = 1_000_000
UNMET_PENALTY = 100.0
STABILITY_PENALTY = 0.0005
DEFAULT_WEIGHTS = {"cost": 0.7, "carbon": 0.3, "lateness": 1.0}
# CP-SAT stops once the plan is proven within this fraction of the best possible objective.
RELATIVE_GAP_LIMIT = 0.005
# Search effort in deterministic time units (about seconds here). Unlike a wall-clock limit,
# this gives the same plan on every machine; the wall-clock limit is only a safety net.
DETERMINISTIC_TIME = 6.0


@dataclass
class PlanResult:
    status: str  # OPTIMAL | FEASIBLE | GREEDY | INFEASIBLE
    solver: str  # cpsat | greedy
    chosen: dict[str, Option]  # order_id -> Option
    unmet: list[str]  # order ids with no assignment
    solve_ms: int
    fallback: bool = field(default=False)
    gap_pct: float | None = field(default=None)  # proven distance from the best bound


def coefficients(
    options: list[Option], weights: dict, base_assignment: dict | None = None
) -> list[float]:
    cheapest = cheapest_option_per_order(options)
    c_ref = sum(o.cost for o in cheapest.values()) or 1.0
    greenest: dict[str, Option] = {}
    for o in options:
        if o.order_id not in greenest or o.carbon_kg < greenest[o.order_id].carbon_kg:
            greenest[o.order_id] = o
    g_ref = sum(o.carbon_kg for o in greenest.values()) or 1.0
    wc, wg = weights["cost"], weights["carbon"]
    total = (wc + wg) or 1.0
    wc, wg = wc / total, wg / total  # cost and carbon weights sum to 1
    wl = weights.get("lateness", 1.0)
    coef = []
    for o in options:
        v = wc * o.cost / c_ref + wg * o.carbon_kg / g_ref
        if o.days_late > 0:
            v += wl * (1.0 + 0.01 * o.days_late)  # one late order outweighs the cost term
        if base_assignment and base_assignment.get(o.order_id) not in (None, o.plant):
            v += STABILITY_PENALTY  # prefer not moving an order
        v += 1e-7 * o.week  # tie-break: earlier week
        coef.append(v)
    return coef


def objective_value(
    options: list[Option],
    result: PlanResult,
    weights: dict,
    base_assignment: dict | None = None,
) -> float:
    """The weighted score of a plan, comparable between solvers."""
    coef = coefficients(options, weights, base_assignment)
    index = {(o.order_id, o.plant, o.week): i for i, o in enumerate(options)}
    chosen = sum(coef[index[(o.order_id, o.plant, o.week)]] for o in result.chosen.values())
    planned = {o.order_id for o in options}
    return chosen + UNMET_PENALTY * sum(1 for oid in result.unmet if oid in planned)


def solve_cpsat(
    options: list[Option],
    capacity: dict,
    weights: dict,
    *,
    carbon_cap_kg: float | None = None,
    on_time_only: bool = False,
    base_assignment: dict | None = None,
    time_limit_s: float = 10,
) -> PlanResult:
    t0 = time.time()
    coef = coefficients(options, weights, base_assignment)
    model = cp_model.CpModel()
    x: dict[int, cp_model.IntVar] = {}
    by_order: dict[str, list[int]] = defaultdict(list)
    by_cap: dict[tuple, list[int]] = defaultdict(list)
    order_ids = sorted({o.order_id for o in options})
    for i, o in enumerate(options):
        if on_time_only and o.days_late > 0:
            continue
        x[i] = model.new_bool_var(f"x{i}")
        by_order[o.order_id].append(i)
        by_cap[(o.plant, o.product, o.week)].append(i)
    unmet_var = {oid: model.new_bool_var(f"u_{oid}") for oid in order_ids}
    for oid in order_ids:
        model.add(sum(x[i] for i in by_order[oid]) + unmet_var[oid] == 1)
    for key, idxs in by_cap.items():
        model.add(sum(options[i].qty * x[i] for i in idxs) <= int(capacity.get(key, 0)))
    if carbon_cap_kg is not None:
        model.add(sum(int(round(options[i].carbon_kg)) * x[i] for i in x) <= int(carbon_cap_kg))
    # Two valid cuts from tiny exact solves close most of the bound gap: no plan can deliver
    # more orders on time, or assign more orders, than capacity allows.
    on_time = [i for i in x if options[i].days_late == 0]
    if on_time:
        most = max_count(options, capacity, on_time)
        if most:
            model.add(sum(x[i] for i in on_time) <= most[0])
    if x:
        best = max_count(options, capacity, list(x), carbon_cap_kg)
        if best:
            model.add(sum(unmet_var.values()) >= len(order_ids) - best[0])
    model.minimize(
        sum(int(round(SCALE * coef[i])) * x[i] for i in x)
        + sum(int(SCALE * UNMET_PENALTY) * u for u in unmet_var.values())
    )
    solver = _solver(time_limit_s)
    status = solver.solve(model)
    elapsed = int((time.time() - t0) * 1000)
    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return PlanResult("INFEASIBLE", "cpsat", {}, order_ids, elapsed)
    chosen = {options[i].order_id: options[i] for i in x if solver.value(x[i]) == 1}
    unmet = [oid for oid in order_ids if solver.value(unmet_var[oid]) == 1]
    label = "OPTIMAL" if status == cp_model.OPTIMAL else "FEASIBLE"
    objective = solver.objective_value
    gap = (objective - solver.best_objective_bound) / objective * 100 if objective else 0.0
    return PlanResult(label, "cpsat", chosen, unmet, elapsed, gap_pct=round(max(gap, 0.0), 3))


def _solver(time_limit_s: float) -> cp_model.CpSolver:
    # One worker plus a deterministic-time budget makes the plan reproducible across runs and
    # machines; the gap limit stops the search once the plan is proven near-optimal.
    solver = cp_model.CpSolver()
    params = solver.parameters
    params.num_workers = 1
    params.random_seed = 42
    params.relative_gap_limit = RELATIVE_GAP_LIMIT
    params.max_deterministic_time = min(DETERMINISTIC_TIME, 0.75 * time_limit_s)
    params.max_time_in_seconds = max(time_limit_s, 1.0) * 3  # safety net only
    return solver


def max_count(
    options: list[Option],
    capacity: dict,
    candidates: list[int],
    carbon_cap_kg: float | None = None,
    *,
    count_only: list[int] | None = None,
    assigned: int | None = None,
) -> tuple[int, list[int]] | None:
    """Most orders that can take one of `candidates` within capacity (and the carbon cap).

    With `count_only`, count only those options instead, among plans that assign exactly
    `assigned` orders. Returns (count, chosen option indices), or None when not proven."""
    model = cp_model.CpModel()
    y = {i: model.new_bool_var(f"y{i}") for i in candidates}
    by_order: dict[str, list[int]] = defaultdict(list)
    by_cap: dict[tuple, list[int]] = defaultdict(list)
    for i in candidates:
        o = options[i]
        by_order[o.order_id].append(i)
        by_cap[(o.plant, o.product, o.week)].append(i)
    for idxs in by_order.values():
        model.add(sum(y[i] for i in idxs) <= 1)
    for key, idxs in by_cap.items():
        model.add(sum(options[i].qty * y[i] for i in idxs) <= int(capacity.get(key, 0)))
    if carbon_cap_kg is not None:
        model.add(sum(int(round(options[i].carbon_kg)) * y[i] for i in y) <= int(carbon_cap_kg))
    if assigned is not None:
        model.add(sum(y.values()) == assigned)
    counted = count_only if count_only is not None else candidates
    model.maximize(sum(y[i] for i in counted))
    # Parallel workers are fine here: only the optimal count is used, and it is unique.
    solver = cp_model.CpSolver()
    solver.parameters.num_workers = 8
    solver.parameters.max_time_in_seconds = 5
    if solver.solve(model) == cp_model.OPTIMAL:
        return int(round(solver.objective_value)), [i for i in y if solver.value(y[i])]
    return None


def solve_greedy(
    options: list[Option],
    capacity: dict,
    weights: dict,
    *,
    on_time_only: bool = False,
    base_assignment: dict | None = None,
    **_,
) -> PlanResult:
    """Orders by due date, biggest first; each takes its lowest-score option that still fits."""
    t0 = time.time()
    coef = coefficients(options, weights, base_assignment)
    remaining = dict(capacity)
    candidates: dict[str, list[tuple[float, int]]] = defaultdict(list)
    for i, o in enumerate(options):
        if on_time_only and o.days_late > 0:
            continue
        candidates[o.order_id].append((coef[i], i))
    first = {}
    for o in options:
        first.setdefault(o.order_id, o)
    sequence = sorted(first.values(), key=lambda o: (o.due, -o.qty, o.order_id))

    chosen: dict[str, Option] = {}
    unmet: list[str] = []
    for order in sequence:
        for _, i in sorted(candidates[order.order_id]):
            option = options[i]
            key = (option.plant, option.product, option.week)
            if remaining.get(key, 0) >= option.qty:
                remaining[key] -= option.qty
                chosen[order.order_id] = option
                break
        else:
            unmet.append(order.order_id)
    return PlanResult("GREEDY", "greedy", chosen, sorted(unmet), int((time.time() - t0) * 1000))


# --- Public entry point (the solve_allocation tool) ------------------------------------------


@dataclass
class PlanContext:
    """Everything a plan is computed from, shared by the solver, explanations and trade-offs."""

    start: date
    n_weeks: int
    orders: pd.DataFrame
    options: list[Option]
    events: list[dict]
    capacity: dict
    capacity_base: dict
    scenario: dict


def data_events(events_table: pd.DataFrame) -> list[dict]:
    if events_table.empty:
        return []
    scale = pct_scale(list(events_table["capacity_loss_pct"]))
    return [
        {
            "event_id": row.event_id,
            "plant": row.plant,
            "from_date": row.from_date,
            "to_date": row.to_date,
            "loss": to_fraction(float(row.capacity_loss_pct), scale),
            "source": "data",
        }
        for row in events_table.itertuples()
    ]


def plan_context(tables: dict, settings, scenario: dict | None = None) -> PlanContext:
    scenario = normalise_scenario(scenario)
    all_orders = tables["orders"]
    start = planning_start(all_orders, settings)
    n_weeks = horizon_weeks(all_orders, start)
    horizon_end = week_start(start, n_weeks) - timedelta(days=1)

    orders = all_orders
    if scenario["only_orders"] is not None:
        orders = orders.loc[orders["order_id"].isin(scenario["only_orders"])]
    if scenario["exclude_orders"]:
        orders = orders.loc[~orders["order_id"].isin(scenario["exclude_orders"])]

    options = build_options({**tables, "orders": orders}, start, n_weeks, settings)
    if scenario["exclude_plants"]:
        options = [o for o in options if o.plant not in scenario["exclude_plants"]]

    events = [] if scenario["ignore_events"] else data_events(tables["capacity_events"])
    for item in scenario["capacity_loss"]:
        events.append(
            {
                "event_id": None,
                "plant": item["plant"],
                "from_date": item["from_date"] or start,
                "to_date": item["to_date"] or horizon_end,
                "loss": normalise_pct(item["pct"]),
                "source": "scenario",
            }
        )
    return PlanContext(
        start=start,
        n_weeks=n_weeks,
        orders=orders,
        options=options,
        events=events,
        capacity=effective_capacity(tables["plants"], events, start, n_weeks),
        capacity_base=base_capacity(tables["plants"], start, n_weeks),
        scenario=scenario,
    )


def run_solver(
    ctx: PlanContext,
    settings,
    weights: dict,
    *,
    base_assignment: dict | None = None,
    solver: str | None = None,
    carbon_cap_kg: float | None = None,
    time_limit_s: float | None = None,
) -> PlanResult:
    name = solver or settings.solver
    kwargs = {
        "carbon_cap_kg": carbon_cap_kg,
        "on_time_only": ctx.scenario["on_time_only"],
        "base_assignment": base_assignment,
        "time_limit_s": time_limit_s or settings.solver_time_limit_s,
    }
    if name == "greedy":
        result = solve_greedy(ctx.options, ctx.capacity, weights, **kwargs)
    else:
        try:
            result = solve_cpsat(ctx.options, ctx.capacity, weights, **kwargs)
        except Exception:  # any CP-SAT failure: fall back rather than fail the request
            result = solve_greedy(ctx.options, ctx.capacity, weights, **kwargs)
            result.fallback = True
    # Orders with no option at all (no eligible plant or lane) are unmet too.
    with_options = {o.order_id for o in ctx.options}
    missing = [oid for oid in ctx.orders["order_id"] if oid not in with_options]
    result.unmet = sorted(set(result.unmet) | set(missing))
    return result


def option_row(o: Option) -> dict:
    return {
        "order_id": o.order_id,
        "plant": o.plant,
        "week": o.week,
        "cost": o.cost,
        "carbon_kg": o.carbon_kg,
        "arrival": o.arrival.isoformat(),
        "on_time": o.on_time,
        "days_late": o.days_late,
        "production": o.production,
        "energy": o.energy,
        "transport": o.transport,
        "duty": o.duty,
        "qty": o.qty,
        "product": o.product,
        "destination": o.destination,
        "due": o.due.isoformat(),
        "moved": False,
        "base_plant": None,
    }


def kpis(rows: list[dict], unmet: list[str], capacity: dict) -> dict:
    """Plan totals. Utilisation is assigned quantity over the plant's effective capacity
    summed over the horizon."""
    plants = sorted({key[0] for key in capacity})
    orders_total = len(rows) + len(unmet)
    assigned_qty: dict[str, int] = defaultdict(int)
    count: dict[str, int] = defaultdict(int)
    for row in rows:
        assigned_qty[row["plant"]] += row["qty"]
        count[row["plant"]] += 1
    plant_capacity: dict[str, int] = defaultdict(int)
    for (plant, _product, _week), amount in capacity.items():
        plant_capacity[plant] += amount
    return {
        "total_cost": round(sum(r["cost"] for r in rows), 2),
        "total_carbon_t": round(sum(r["carbon_kg"] for r in rows) / 1000, 3),
        "late_orders": sum(1 for r in rows if r["days_late"] > 0),
        "unmet_orders": len(unmet),
        "orders_total": orders_total,
        "plant_share": {
            p: round(count[p] / orders_total, 3) if orders_total else 0.0 for p in plants
        },
        "plant_utilisation": {
            p: round(assigned_qty[p] / plant_capacity[p], 3) if plant_capacity[p] else 0.0
            for p in plants
        },
    }


def capacity_records(ctx: PlanContext, rows: list[dict]) -> list[dict]:
    used: dict[tuple, int] = defaultdict(int)
    for row in rows:
        used[(row["plant"], row["product"], row["week"])] += row["qty"]
    return [
        {
            "plant": plant,
            "product": product,
            "week": week,
            "week_start": week_start(ctx.start, week).isoformat(),
            "base": ctx.capacity_base.get((plant, product, week), 0),
            "effective": amount,
            "used": used.get((plant, product, week), 0),
        }
        for (plant, product, week), amount in sorted(ctx.capacity.items())
    ]


def plan_dict(ctx: PlanContext, result: PlanResult, weights: dict, carbon_cap_kg=None) -> dict:
    rows = [option_row(o) for o in sorted(result.chosen.values(), key=lambda o: o.order_id)]
    return {
        "status": result.status,
        "solver": result.solver,
        "fallback": result.fallback,
        "solve_ms": result.solve_ms,
        "gap_pct": result.gap_pct,
        "start": ctx.start.isoformat(),
        "n_weeks": ctx.n_weeks,
        "weights": dict(weights),
        "scenario": scenario_json(ctx.scenario),
        "carbon_cap_kg": carbon_cap_kg,
        "events": [
            {
                "event_id": e["event_id"],
                "plant": e["plant"],
                "from_date": e["from_date"].isoformat(),
                "to_date": e["to_date"].isoformat(),
                "loss_pct": round(e["loss"] * 100, 1),
                "source": e["source"],
            }
            for e in ctx.events
        ],
        "rows": rows,
        "unmet": result.unmet,
        "kpis": kpis(rows, result.unmet, ctx.capacity),
        "capacity": capacity_records(ctx, rows),
    }


def solve_allocation(
    tables: dict,
    settings,
    weights: dict,
    scenario: dict | None = None,
    base_assignment: dict | None = None,
    solver: str | None = None,
    *,
    carbon_cap_kg: float | None = None,
    time_limit_s: float | None = None,
) -> dict:
    """Plan every order: returns rows, unmet orders, KPIs and capacity use as plain data."""
    ctx = plan_context(tables, settings, scenario)
    result = run_solver(
        ctx,
        settings,
        weights,
        base_assignment=base_assignment,
        solver=solver,
        carbon_cap_kg=carbon_cap_kg,
        time_limit_s=time_limit_s,
    )
    return plan_dict(ctx, result, weights, carbon_cap_kg)
