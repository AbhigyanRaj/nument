"""Plan comparison, the cost-carbon trade-off, order explanations and recommendations.

Every number here is computed by code from solver output; the LLM only rephrases them.
"""

from __future__ import annotations

from collections import defaultdict

from app.core.costing import Pricing, cheapest_option_per_order
from app.core.solver import coefficients, plan_context, solve_allocation

DUTY_SHARE_LIMIT = 0.15  # duty above this share of landed cost makes a plant expensive


def _pct(part: float, whole: float) -> float | None:
    return round(100.0 * part / whole, 2) if whole else None


# --- compare_plans -----------------------------------------------------------------------------


def compare_plans(base: dict, new: dict) -> dict:
    """What changed from `base` to `new`. Also marks `moved` and `base_plant` on new's rows."""
    base_rows = {r["order_id"]: r for r in base["rows"]}
    new_rows = {r["order_id"]: r for r in new["rows"]}
    orders = sorted(set(base_rows) | set(new_rows) | set(base["unmet"]) | set(new["unmet"]))

    moved = []
    for oid in orders:
        before, after = base_rows.get(oid), new_rows.get(oid)
        from_plant = before["plant"] if before else None
        to_plant = after["plant"] if after else None
        if after is not None:
            after["base_plant"] = from_plant
            after["moved"] = from_plant != to_plant
        if from_plant == to_plant:
            continue
        moved.append(
            {
                "order_id": oid,
                "from_plant": from_plant,
                "to_plant": to_plant,
                "cost_change": round(
                    (after["cost"] if after else 0) - (before["cost"] if before else 0), 2
                ),
                "carbon_change_kg": round(
                    (after["carbon_kg"] if after else 0) - (before["carbon_kg"] if before else 0), 3
                ),
                "became_late": bool(
                    after and after["days_late"] > 0 and not (before and before["days_late"] > 0)
                ),
            }
        )
    moved.sort(key=lambda m: (-m["cost_change"], m["order_id"]))

    bk, nk = base["kpis"], new["kpis"]
    extra_cost = round(nk["total_cost"] - bk["total_cost"], 2)
    extra_carbon = round(nk["total_carbon_t"] - bk["total_carbon_t"], 3)
    kept = len(orders) - len(moved)
    return {
        "extra_cost": extra_cost,
        "extra_cost_pct": _pct(extra_cost, bk["total_cost"]),
        "extra_carbon_t": extra_carbon,
        "extra_carbon_pct": _pct(extra_carbon, bk["total_carbon_t"]),
        "late_orders_change": nk["late_orders"] - bk["late_orders"],
        "unmet_change": nk["unmet_orders"] - bk["unmet_orders"],
        "moved_count": len(moved),
        "stability_pct": round(100.0 * kept / len(orders), 1) if orders else 100.0,
        "moved": moved,
    }


# --- trade-off and weight sweep ----------------------------------------------------------------


def _carbon_kg(plan: dict) -> float:
    return sum(r["carbon_kg"] for r in plan["rows"])


def tradeoff_table(
    tables: dict,
    settings,
    weights: dict,
    scenario: dict | None = None,
    cuts=(0, 5, 10, 15, 20),
    time_limit_s: float = 4,
) -> list[dict]:
    """Cost of cutting carbon by each percentage against the cost-first plan."""
    cost_first = {"cost": 1.0, "carbon": 0.0, "lateness": weights.get("lateness", 1.0)}
    ref = solve_allocation(tables, settings, cost_first, scenario, time_limit_s=time_limit_s)
    c0 = _carbon_kg(ref)
    ref_cost, ref_unmet = ref["kpis"]["total_cost"], ref["kpis"]["unmet_orders"]
    rows = []
    for cut in sorted({float(c) for c in cuts}):
        plan = (
            ref
            if cut == 0
            else solve_allocation(
                tables,
                settings,
                cost_first,
                scenario,
                carbon_cap_kg=c0 * (1 - cut / 100.0),
                time_limit_s=time_limit_s,
            )
        )
        k = plan["kpis"]
        extra = round(k["total_cost"] - ref_cost, 2)
        saved_t = (c0 - _carbon_kg(plan)) / 1000.0
        rows.append(
            {
                "carbon_cut_pct": int(cut) if cut == int(cut) else cut,
                "cost": k["total_cost"],
                "carbon_t": k["total_carbon_t"],
                "late_orders": k["late_orders"],
                "unmet_orders": k["unmet_orders"],
                "extra_cost": extra,
                "extra_cost_pct": _pct(extra, ref_cost),
                "cost_per_tonne_saved": round(extra / saved_t, 2) if saved_t > 1e-9 else None,
                # Carbon that only fell because orders were dropped is not a real saving.
                "feasible": k["unmet_orders"] <= ref_unmet,
            }
        )
    return rows


def weight_sweep(
    tables: dict,
    settings,
    scenario: dict | None = None,
    grid=((1, 0), (0.7, 0.3), (0.5, 0.5), (0.3, 0.7), (0, 1)),
    time_limit_s: float = 4,
) -> list[dict]:
    rows = []
    for cost_w, carbon_w in grid:
        plan = solve_allocation(
            tables,
            settings,
            {"cost": cost_w, "carbon": carbon_w, "lateness": 1.0},
            scenario,
            time_limit_s=time_limit_s,
        )
        k = plan["kpis"]
        rows.append(
            {
                "cost_weight": cost_w,
                "carbon_weight": carbon_w,
                "cost": k["total_cost"],
                "carbon_t": k["total_carbon_t"],
                "late_orders": k["late_orders"],
                "plant_share": k["plant_share"],
            }
        )
    return rows


def baseline_cheapest_plan(tables: dict, settings, scenario: dict | None = None) -> dict:
    """The rule of thumb: cheapest plant for every order, ignoring dates (greedy)."""
    return solve_allocation(
        tables, settings, {"cost": 1.0, "carbon": 0.0, "lateness": 0.0}, scenario, solver="greedy"
    )


# --- explain_order -----------------------------------------------------------------------------


def _option_row(option, chosen: bool, capacity_left: int) -> dict:
    return {
        "plant": option.plant,
        "eligible": True,
        "week": option.week,
        "cost": option.cost,
        "production": option.production,
        "energy": option.energy,
        "transport": option.transport,
        "duty": option.duty,
        "carbon_kg": option.carbon_kg,
        "arrival": option.arrival.isoformat(),
        "on_time": option.on_time,
        "days_late": option.days_late,
        "capacity_left_in_week": capacity_left,
        "chosen": chosen,
    }


def explain_order(
    order_id: str, plan: dict, tables: dict, settings, scenario: dict | None = None
) -> dict:
    """One row per plant for this order (the chosen week at the chosen plant, each other
    plant's best week by the plan's objective), plus reason codes computed by code."""
    orders = tables["orders"]
    match = orders.loc[orders["order_id"] == order_id]
    if match.empty:
        return {"found": False, "order_id": order_id}
    order = next(match.itertuples())

    ctx = plan_context(tables, settings, scenario if scenario is not None else plan.get("scenario"))
    pricing = Pricing(tables, ctx.start, settings)
    weights = plan.get("weights") or {"cost": 0.7, "carbon": 0.3, "lateness": 1.0}
    coef = coefficients(ctx.options, weights)
    mine = [(c, o) for c, o in zip(coef, ctx.options, strict=True) if o.order_id == order_id]

    used: dict[tuple, int] = defaultdict(int)
    for row in plan["rows"]:
        used[(row["plant"], row["product"], row["week"])] += row["qty"]
    chosen_row = next((r for r in plan["rows"] if r["order_id"] == order_id), None)

    def left(plant: str, week: int) -> int:
        key = (plant, order.product, week)
        return ctx.capacity.get(key, 0) - used.get(key, 0)

    plants = sorted(set(tables["plants"]["plant"]))
    rows = []
    for plant in plants:
        if not pricing.eligible(plant, order.product, order.destination):
            rows.append({"plant": plant, "eligible": False, "chosen": False})
            continue
        if chosen_row and chosen_row["plant"] == plant:
            option = pricing.option(order, plant, chosen_row["week"])
            rows.append(_option_row(option, True, left(plant, option.week)))
            continue
        candidates = [(c, o) for c, o in mine if o.plant == plant]
        if not candidates:
            rows.append({"plant": plant, "eligible": False, "chosen": False})
            continue
        option = min(candidates, key=lambda co: (co[0], co[1].week))[1]
        rows.append(_option_row(option, False, left(plant, option.week)))

    return {
        "found": True,
        "order_id": order_id,
        "product": order.product,
        "qty": int(order.qty),
        "destination": order.destination,
        "due": order.due.isoformat(),
        "chosen_plant": chosen_row["plant"] if chosen_row else None,
        "unmet": chosen_row is None,
        "rows": rows,
        "reason_codes": _reason_codes(order, [o for _, o in mine], rows, chosen_row, left),
    }


def _reason_codes(order, options, rows, chosen_row, left) -> list[dict]:
    codes: list[dict] = []
    eligible = [r for r in rows if r.get("eligible")]
    if len(eligible) == 1:
        codes.append(
            {
                "code": "ONLY_ELIGIBLE_PLANT",
                "plant": eligible[0]["plant"],
                "detail": f"only plant {eligible[0]['plant']} can make {order.product} for {order.destination}",
            }
        )
    if not options:
        return codes
    cheapest = cheapest_option_per_order(options)[order.order_id]
    chosen = next((r for r in rows if r.get("chosen")), None)
    if cheapest.days_late > 0 and any(o.on_time for o in options):
        codes.append(
            {
                "code": "CHEAPEST_OPTION_LATE",
                "plant": cheapest.plant,
                "detail": (
                    f"plant {cheapest.plant} is cheapest but arrives {cheapest.arrival.isoformat()}, "
                    f"{cheapest.days_late} days after the {order.due.isoformat()} due date"
                ),
            }
        )
    for row in eligible:
        if row["cost"] and row["duty"] / row["cost"] > DUTY_SHARE_LIMIT:
            codes.append(
                {
                    "code": "DUTY_MAKES_PLANT_EXPENSIVE",
                    "plant": row["plant"],
                    "detail": f"duty is {row['duty'] / row['cost']:.0%} of plant {row['plant']}'s landed cost",
                }
            )
    if chosen and chosen["plant"] != cheapest.plant and chosen["carbon_kg"] < cheapest.carbon_kg:
        codes.append(
            {
                "code": "LOWER_CARBON",
                "plant": chosen["plant"],
                "detail": (
                    f"plant {chosen['plant']} emits {chosen['carbon_kg']:.1f} kg CO2e against "
                    f"{cheapest.carbon_kg:.1f} kg at plant {cheapest.plant}"
                ),
            }
        )
    if chosen:
        for plant in sorted({o.plant for o in options} - {chosen["plant"]}):
            on_time = [o for o in options if o.plant == plant and o.on_time]
            if not on_time or min(o.cost for o in on_time) >= chosen["cost"]:
                continue
            if all(left(plant, o.week) < order.qty for o in on_time):
                codes.append(
                    {
                        "code": "CAPACITY_FULL_AT_CHEAPER_PLANT",
                        "plant": plant,
                        "detail": f"plant {plant} is cheaper on time but has no room for {order.qty} units in those weeks",
                    }
                )
    return codes


# --- recommendations -----------------------------------------------------------------------------


def recommendations(
    plan: dict,
    comparison: dict | None = None,
    tradeoff: list[dict] | None = None,
    check: dict | None = None,
) -> list[dict]:
    """Next actions built from facts. Numbers are raw; wording is plain and deterministic."""
    flags_ok = bool(check) and all(v for k, v in check.items() if k.endswith("_ok"))
    confidence = "high" if plan.get("status") == "OPTIMAL" and flags_ok else "medium"
    k = plan["kpis"]
    items: list[dict] = []

    if comparison and comparison["moved_count"]:
        losers: dict[str, int] = defaultdict(int)
        for m in comparison["moved"]:
            if m["from_plant"]:
                losers[m["from_plant"]] += 1
        source = max(sorted(losers), key=lambda p: losers[p]) if losers else None
        ids = [m["order_id"] for m in comparison["moved"][:5]]
        items.append(
            {
                "action": f"Approve re-plan: move {comparison['moved_count']} orders"
                + (f" off Plant {source}" if source else ""),
                "rationale": "Keeps every plant within its reduced capacity.",
                "evidence_refs": ["tool:compare_plans", "orders:" + ",".join(ids)],
                "confidence": confidence,
                "estimated_impact": {
                    "cost": comparison["extra_cost"],
                    "carbon_t": comparison["extra_carbon_t"],
                },
                "requires_approval": True,
            }
        )
    if k["unmet_orders"]:
        ids = plan["unmet"][:5]
        items.append(
            {
                "action": f"Decide on {k['unmet_orders']} orders that cannot be made",
                "rationale": "No plant has room for them within the horizon: add capacity or renegotiate dates.",
                "evidence_refs": ["tool:solve_allocation", "orders:" + ",".join(ids)],
                "confidence": confidence,
                "estimated_impact": {"unmet_orders": k["unmet_orders"]},
                "requires_approval": True,
            }
        )
    if k["late_orders"]:
        late = [r["order_id"] for r in plan["rows"] if r["days_late"] > 0][:5]
        items.append(
            {
                "action": f"Tell customers about {k['late_orders']} late orders",
                "rationale": "No plant can deliver them by their due date within capacity.",
                "evidence_refs": ["tool:solve_allocation", "orders:" + ",".join(late)],
                "confidence": confidence,
                "estimated_impact": {"late_orders": k["late_orders"]},
                "requires_approval": False,
            }
        )
    if tradeoff:
        feasible = [
            r
            for r in tradeoff
            if r["feasible"] and r["carbon_cut_pct"] > 0 and r["cost_per_tonne_saved"] is not None
        ]
        if feasible:
            best = min(feasible, key=lambda r: (r["cost_per_tonne_saved"], -r["carbon_cut_pct"]))
            ref = next((r for r in tradeoff if r["carbon_cut_pct"] == 0), None)
            saved = round(ref["carbon_t"] - best["carbon_t"], 3) if ref else None
            items.append(
                {
                    "action": f"Consider a {best['carbon_cut_pct']}% carbon cut",
                    "rationale": "It saves carbon at the lowest cost per tonne on the trade-off table.",
                    "evidence_refs": ["tool:tradeoff_table"],
                    "confidence": confidence,
                    "estimated_impact": {
                        "cost": best["extra_cost"],
                        "carbon_t": -saved if saved is not None else None,
                    },
                    "requires_approval": True,
                }
            )
    if not items:
        items.append(
            {
                "action": "Approve the plan as computed",
                "rationale": "Every order is on time within capacity.",
                "evidence_refs": ["tool:solve_allocation", "tool:validate_plan"],
                "confidence": confidence,
                "estimated_impact": {"cost": k["total_cost"], "carbon_t": k["total_carbon_t"]},
                "requires_approval": True,
            }
        )
    return items
