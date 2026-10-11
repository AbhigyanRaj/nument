"""The six dataset checks, run after every load.

A failing V1, V2 or V4 never stops planning: the affected orders simply have fewer (or no)
options and are reported as unmet. `ok` reflects all six checks.
"""

from __future__ import annotations

from datetime import date

import pandas as pd

from app.core.calendar import pct_scale

CARBON_PER_KWH_MAX = 2.0  # kg CO2e per kWh; above this a grid intensity is not plausible
LIST_LIMIT = 10  # offenders named in a detail line


def validate_dataset(
    tables: dict[str, pd.DataFrame],
    planning_start: date,
    expected_counts: dict[str, int] | None = None,
) -> dict:
    orders = tables["orders"]
    plants = tables["plants"]
    lanes = tables["transport_duties"]
    events = tables["capacity_events"]
    counts = {name: len(frame) for name, frame in tables.items()}

    checks = [
        _check_products(orders, plants),
        _check_lanes(orders, plants, lanes),
        _check_capacity(plants),
        _check_due_dates(orders, planning_start),
        _check_carbon(plants, lanes),
        _check_counts(counts, expected_counts),
    ]
    return {
        "ok": all(c["ok"] for c in checks),
        "checks": checks,
        "units": _units(lanes, events),
        "planning_start": planning_start.isoformat(),
        "row_counts": counts,
    }


def _check(check_id: str, name: str, ok: bool, detail: str) -> dict:
    return {"id": check_id, "name": name, "ok": ok, "detail": detail}


def _named(items: list[str]) -> str:
    shown = ", ".join(items[:LIST_LIMIT])
    more = len(items) - LIST_LIMIT
    return shown + (f" and {more} more" if more > 0 else "")


def _check_products(orders: pd.DataFrame, plants: pd.DataFrame) -> dict:
    makeable = set(plants["product"])
    offenders = sorted(orders.loc[~orders["product"].isin(makeable), "order_id"])
    if offenders:
        detail = (
            f"{len(offenders)} orders have no plant that makes their product: {_named(offenders)}"
        )
    else:
        detail = f"all {len(orders)} orders have at least one plant that makes their product"
    return _check(
        "V1", "Every order's product is made by at least one plant", not offenders, detail
    )


def _check_lanes(orders: pd.DataFrame, plants: pd.DataFrame, lanes: pd.DataFrame) -> dict:
    existing = set(zip(lanes["plant"], lanes["destination"], strict=True))
    needed = [
        (p, d) for p in sorted(set(plants["plant"])) for d in sorted(set(orders["destination"]))
    ]
    missing = [f"{p} to {d}" for p, d in needed if (p, d) not in existing]
    if missing:
        detail = f"{len(missing)} plant-destination pairs have no transport row: {_named(missing)}"
    else:
        detail = f"all {len(needed)} plant-destination pairs have a transport row"
    return _check("V2", "Every plant-destination pair has a transport row", not missing, detail)


def _check_capacity(plants: pd.DataFrame) -> dict:
    if plants.empty:
        return _check("V3", "Capacity is positive", False, "no plant rows loaded, so no capacity")
    bad = plants.loc[~(plants["weekly_capacity"] > 0)]
    offenders = [f"{r.plant} {r.product}" for r in bad.itertuples()]
    if offenders:
        detail = (
            f"{len(offenders)} rows have no positive capacity: {_named(offenders)} (units per week)"
        )
    else:
        low, high = int(plants["weekly_capacity"].min()), int(plants["weekly_capacity"].max())
        detail = f"all {len(plants)} rows positive, {low:,} to {high:,} units per week"
    return _check("V3", "Capacity is positive", not offenders, detail)


def _check_due_dates(orders: pd.DataFrame, start: date) -> dict:
    offenders = sorted(orders.loc[orders["due"].map(lambda d: d <= start), "order_id"])
    if offenders:
        detail = (
            f"{len(offenders)} orders are due on or before the planning start "
            f"{start.isoformat()}: {_named(offenders)}"
        )
    else:
        detail = f"all due dates are after the planning start {start.isoformat()}"
    return _check("V4", "Due dates are after the planning start", not offenders, detail)


def _check_carbon(plants: pd.DataFrame, lanes: pd.DataFrame) -> dict:
    grid = plants["carbon_kg_per_kwh"]
    freight = lanes["carbon_kg_per_unit"]
    bad_grid = plants.loc[(grid < 0) | (grid > CARBON_PER_KWH_MAX)]
    bad_freight = lanes.loc[freight < 0]
    problems = [f"{r.plant} {r.product} grid {r.carbon_kg_per_kwh}" for r in bad_grid.itertuples()]
    problems += [
        f"{r.plant} to {r.destination} transport {r.carbon_kg_per_unit}"
        for r in bad_freight.itertuples()
    ]
    if problems:
        detail = f"{len(problems)} values out of range: {_named(problems)}"
    else:
        grid_part = (
            f"grid {grid.min():.2f} to {grid.max():.2f} kg CO2e per kWh "
            f"(allowed 0 to {CARBON_PER_KWH_MAX:g})"
            if not plants.empty
            else "no plant rows"
        )
        freight_part = (
            f"transport {freight.min():.2f} to {freight.max():.2f} kg CO2e per unit"
            if not lanes.empty
            else "no transport rows"
        )
        detail = f"{grid_part}; {freight_part}"
    return _check("V5", "Carbon intensities are non-negative and plausible", not problems, detail)


def _check_counts(counts: dict[str, int], expected: dict[str, int] | None) -> dict:
    reported = ", ".join(f"{name} {n}" for name, n in counts.items())
    if not expected:
        return _check(
            "V6",
            "Row counts match the data card",
            True,
            f"no data card for this dataset, counts reported: {reported}",
        )
    mismatches = [
        f"{name} {counts.get(name, 0)} (card says {n})"
        for name, n in expected.items()
        if counts.get(name, 0) != n
    ]
    if mismatches:
        detail = f"counts differ from the data card: {', '.join(mismatches)}"
    else:
        detail = f"counts match the data card: {', '.join(f'{k} {v}' for k, v in expected.items())}"
    return _check("V6", "Row counts match the data card", not mismatches, detail)


def _units(lanes: pd.DataFrame, events: pd.DataFrame) -> dict:
    def scale(values, label: str) -> str:
        if len(values) == 0:
            return f"{label}: no rows yet"
        kind = pct_scale(values)
        reason = "values above 1 found" if kind == "percent" else "all values between 0 and 1"
        return f"{label}: read as {kind} ({reason})"

    return {
        "weekly_capacity": "units per week, per plant and product",
        "unit_cost": "currency per unit",
        "transport_cost_per_unit": "currency per unit",
        "energy_kwh_per_unit": "kWh per unit",
        "energy_price_per_kwh": "currency per kWh (blank uses DEFAULT_ENERGY_PRICE_PER_KWH)",
        "carbon_kg_per_kwh": "kg CO2e per kWh",
        "carbon_kg_per_unit": "kg CO2e per unit",
        "duty_pct": scale(list(lanes["duty_pct"]), "duty_pct"),
        "capacity_loss_pct": scale(list(events["capacity_loss_pct"]), "capacity_loss_pct"),
    }
