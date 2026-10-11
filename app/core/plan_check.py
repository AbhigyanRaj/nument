"""Independent plan validator (the validate_plan tool).

Everything is recomputed from the raw tables; nothing the solver reported is trusted.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date

from app.core.costing import Pricing
from app.core.solver import plan_context

VIOLATIONS_RETURNED = 20
TOLERANCE = 0.01


def validate_plan(plan: dict, tables: dict, settings, scenario: dict | None = None) -> dict:
    ctx = plan_context(tables, settings, scenario if scenario is not None else plan.get("scenario"))
    pricing = Pricing(tables, ctx.start, settings)
    orders = {row.order_id: row for row in ctx.orders.itertuples()}
    violations: list[str] = []
    flags = {
        "capacity_ok": True,
        "eligibility_ok": True,
        "delivery_ok": True,
        "complete_ok": True,
        "numbers_ok": True,
    }

    def fail(flag: str, message: str) -> None:
        flags[flag] = False
        violations.append(message)

    # Capacity: quantity per (plant, product, week) within recomputed effective capacity.
    used: dict[tuple, int] = defaultdict(int)
    for row in plan["rows"]:
        used[(row["plant"], row["product"], row["week"])] += int(row["qty"])
    for key, qty in sorted(used.items()):
        limit = ctx.capacity.get(key, 0)
        if qty > limit:
            plant, product, week = key
            fail(
                "capacity_ok",
                f"capacity: {plant} {product} week {week} uses {qty} of {limit} units",
            )

    for row in plan["rows"]:
        oid = row["order_id"]
        order = orders.get(oid)
        if order is None:
            fail("complete_ok", f"complete: {oid} is not an order in the data")
            continue
        if not pricing.eligible(row["plant"], order.product, order.destination):
            fail(
                "eligibility_ok",
                f"eligibility: {oid} at plant {row['plant']} has no plant row for "
                f"{order.product} or no lane to {order.destination}",
            )
            continue
        week = row.get("week")
        if week is None or not 0 <= int(week) < ctx.n_weeks:
            fail("delivery_ok", f"delivery: {oid} has no valid production week")
            continue
        option = pricing.option(order, row["plant"], int(week))
        arrival = date.fromisoformat(str(row["arrival"])[:10])
        if (
            arrival != option.arrival
            or bool(row["on_time"]) != option.on_time
            or int(row["days_late"]) != option.days_late
        ):
            fail(
                "delivery_ok",
                f"delivery: {oid} arrives {option.arrival.isoformat()} "
                f"({option.days_late} days late) but the plan says {row['arrival']} "
                f"(on_time={row['on_time']}, days_late={row['days_late']})",
            )
        if (
            abs(float(row["cost"]) - option.cost) > TOLERANCE
            or abs(float(row["carbon_kg"]) - option.carbon_kg) > TOLERANCE
        ):
            fail(
                "numbers_ok",
                f"numbers: {oid} cost {row['cost']} / carbon {row['carbon_kg']} kg, "
                f"recomputed {option.cost} / {option.carbon_kg} kg",
            )

    # Completeness: every order exactly once, assigned or unmet.
    seen = Counter([r["order_id"] for r in plan["rows"]] + list(plan.get("unmet", [])))
    for oid in sorted(orders):
        if seen[oid] == 0:
            fail("complete_ok", f"complete: {oid} is neither assigned nor unmet")
        elif seen[oid] > 1:
            fail("complete_ok", f"complete: {oid} appears {seen[oid]} times")
    for oid in sorted(set(plan.get("unmet", [])) - set(orders)):
        fail("complete_ok", f"complete: unmet {oid} is not an order in the data")

    return {**flags, "violations": violations[:VIOLATIONS_RETURNED]}
