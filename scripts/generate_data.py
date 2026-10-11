# Creates the made-up (synthetic) dataset: plants, routes and orders,
# with tricky cases built in to test the planner. Same output every run.

"""Generate the synthetic planning dataset (oa-synth v1).

Deterministic: a fixed seed and fixed formatting mean the same command always writes
byte-identical CSVs. No LLM and no real company or personal data are involved.

Outputs
  <out>/plants.csv, transport_duties.csv, orders.csv, capacity_events.csv (header only),
  <out>/row_counts.json (read by validation check V6)
  <drop-out>/capacity_events*.csv  (late data drops used by the demo and the evaluation)

The traps the dataset is built to contain are listed in docs/DATA_CARD.md.
"""

from __future__ import annotations

import argparse
import csv
import json
import random
import sys
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

SEED = 42

# Week 0 starts on this Monday; due dates fall in weeks 1-3.
PLANNING_START = date(2026, 10, 12)
DUE_FIRST = date(2026, 10, 19)
DUE_LAST = date(2026, 11, 8)

PLANTS = ["A", "B", "C"]
PRODUCTS = ["P1", "P2", "P3", "P4", "P5"]
DESTINATIONS = [
    "Germany",
    "France",
    "UK",
    "USA",
    "India",
    "Japan",
    "Brazil",
    "UAE",
    "Singapore",
    "Australia",
    "Mexico",
    "South Africa",
]

# A: cheapest and dirtiest. B: middle. C: dearest, greenest and small.
PLANT_PROFILE = {
    "A": {"unit_cost": (20.0, 26.0), "carbon_kg_per_kwh": 0.82, "energy_price": 0.08},
    "B": {"unit_cost": (24.0, 30.0), "carbon_kg_per_kwh": 0.45, "energy_price": 0.11},
    "C": {"unit_cost": (28.0, 34.0), "carbon_kg_per_kwh": 0.12, "energy_price": 0.14},
}
# Who can make what. P4 is made only at A and P5 only at B (single-plant edge case).
ELIGIBLE = {
    "A": ["P1", "P2", "P3", "P4"],
    "B": ["P1", "P2", "P3", "P5"],
    "C": ["P1", "P2", "P3"],
}
BASE_WEEKLY_CAPACITY = {"A": 2600, "B": 1800, "C": 700}
# The spec suggests 900 (A·P4) and 700 (B·P5), but each of those products carries 10% of
# demand, which puts them at 157% and 212% of four-week capacity: the default plan, and the
# spec's own "B loses 30%" / "A loses 50%" re-plans, would all be infeasible. These values
# keep both feasible with ~15% headroom while the severe B event still leaves P5 short.
SINGLE_PLANT_CAPACITY = {("A", "P4"): 3200, ("B", "P5"): 2300}
ENERGY_KWH_PER_UNIT = {"P1": 4.0, "P2": 6.0, "P3": 5.0, "P4": 8.0, "P5": 7.0}

# Plant B's grid goes dirty for one week.
B_DIRTY_WEEK_START = date(2026, 10, 26)
B_DIRTY_CARBON_KG_PER_KWH = 0.70

# Shipping distance class per (plant, destination): each plant has a home region.
NEAR = {
    "A": {"India", "UAE", "Singapore"},
    "B": {"Germany", "France", "UK"},
    "C": {"USA", "Mexico", "Brazil"},
}
MEDIUM = {
    "A": {"Japan", "Australia", "South Africa"},
    "B": {"UAE", "India", "USA", "South Africa"},
    "C": {"Germany", "France", "UK"},
}
LANE_RANGES = {
    #          transport_cost_per_unit, transit_days, carbon_kg_per_unit
    "near": ((1.0, 2.0), (2, 4), (0.3, 0.6)),
    "medium": ((2.0, 3.5), (5, 8), (0.6, 1.2)),
    "far": ((3.5, 6.0), (9, 16), (1.2, 2.4)),
}
# Rows pinned for the worked example (order O-077) and the duty trap.
PINNED_LANES = {
    ("A", "Germany"): {"transport_cost_per_unit": 4.0, "transit_days": 14, "duty_pct": 4},
    ("C", "Germany"): {"transport_cost_per_unit": 2.2, "transit_days": 5, "duty_pct": 0},
    ("B", "Germany"): {"transit_days": 3},
    ("A", "USA"): {"duty_pct": 28},  # A's low unit cost becomes the dearest landed cost
}

N_ORDERS = 150
PRODUCT_MIX = {"P1": 0.30, "P2": 0.25, "P3": 0.25, "P4": 0.10, "P5": 0.10}
QTY_CHOICES = list(range(50, 601, 10))

# Target share of 4-week capacity taken by total demand (spec: about 70% to 78%).
TARGET_LOAD = 0.70

DROP_FILES = {
    "capacity_events.csv": ["E-001", "B", "2026-10-19", "2026-11-01", 30],
    "capacity_events_severe.csv": ["E-002", "B", "2026-10-19", "2026-11-08", 85],
    "capacity_events_A.csv": ["E-003", "A", "2026-10-12", "2026-10-25", 50],
}

PLANT_COLUMNS = [
    "plant",
    "product",
    "weekly_capacity",
    "unit_cost",
    "energy_kwh_per_unit",
    "carbon_kg_per_kwh",
    "energy_price_per_kwh",
    "week_start",
]
TRANSPORT_COLUMNS = [
    "plant",
    "destination",
    "transport_cost_per_unit",
    "transit_days",
    "duty_pct",
    "carbon_kg_per_unit",
]
ORDER_COLUMNS = ["order_id", "product", "qty", "destination", "due"]
EVENT_COLUMNS = ["event_id", "plant", "from_date", "to_date", "capacity_loss_pct"]


def lane_class(plant: str, destination: str) -> str:
    if destination in NEAR[plant]:
        return "near"
    if destination in MEDIUM[plant]:
        return "medium"
    return "far"


def make_plants(rng: random.Random) -> list[dict]:
    rows = []
    for plant in PLANTS:
        profile = PLANT_PROFILE[plant]
        for product in ELIGIBLE[plant]:
            lo, hi = profile["unit_cost"]
            capacity = SINGLE_PLANT_CAPACITY.get((plant, product), BASE_WEEKLY_CAPACITY[plant])
            kwh = ENERGY_KWH_PER_UNIT[product] * rng.uniform(0.9, 1.1)
            rows.append(
                {
                    "plant": plant,
                    "product": product,
                    "weekly_capacity": capacity,
                    "unit_cost": round(rng.uniform(lo, hi), 2),
                    "energy_kwh_per_unit": round(kwh, 2),
                    "carbon_kg_per_kwh": profile["carbon_kg_per_kwh"],
                    "energy_price_per_kwh": profile["energy_price"],
                    "week_start": "",
                }
            )
    return rows


def add_dirty_week(rows: list[dict]) -> list[dict]:
    """Override rows: Plant B's carbon intensity rises for the week of 26 Oct."""
    overrides = []
    for row in rows:
        if row["plant"] == "B":
            overrides.append(
                {
                    **row,
                    "carbon_kg_per_kwh": B_DIRTY_CARBON_KG_PER_KWH,
                    "week_start": B_DIRTY_WEEK_START.isoformat(),
                }
            )
    return rows + overrides


def make_transport(rng: random.Random) -> list[dict]:
    rows = []
    for plant in PLANTS:
        for destination in DESTINATIONS:
            kind = lane_class(plant, destination)
            (t_lo, t_hi), (d_lo, d_hi), (c_lo, c_hi) = LANE_RANGES[kind]
            row = {
                "plant": plant,
                "destination": destination,
                "transport_cost_per_unit": round(rng.uniform(t_lo, t_hi), 2),
                "transit_days": rng.randint(d_lo, d_hi),
                "duty_pct": 0 if kind == "near" else rng.randint(3, 8),
                "carbon_kg_per_unit": round(rng.uniform(c_lo, c_hi), 2),
            }
            row.update(PINNED_LANES.get((plant, destination), {}))
            rows.append(row)
    return rows


def make_orders(rng: random.Random, n_orders: int = N_ORDERS) -> list[dict]:
    counts = {p: round(share * n_orders) for p, share in PRODUCT_MIX.items()}
    counts["P1"] += n_orders - sum(counts.values())  # absorb rounding
    products = [p for p, n in counts.items() for _ in range(n)]
    rng.shuffle(products)

    span = (DUE_LAST - DUE_FIRST).days
    orders = []
    for i, product in enumerate(products, start=1):
        orders.append(
            {
                "order_id": f"O-{i:03d}",
                "product": product,
                "qty": rng.choice(QTY_CHOICES),
                "destination": rng.choice(DESTINATIONS),
                "due": DUE_FIRST + timedelta(days=rng.randint(0, span)),
            }
        )

    by_id = {o["order_id"]: o for o in orders}

    # Worked example: A ships Fri 16 Oct + 14 days = 30 Oct, three days after the
    # 27 Oct due date; C ships the same day + 5 days = 21 Oct, on time.
    by_id["O-077"].update(product="P1", qty=500, destination="Germany", due=date(2026, 10, 27))

    # More "cheapest plant is late" orders: early-due European orders for P1-P3,
    # where far-away A is cheapest but cannot arrive in time.
    europe = ["Germany", "France", "UK"]
    early_span = (date(2026, 10, 28) - DUE_FIRST).days
    candidates = [
        o for o in orders if o["product"] in {"P1", "P2", "P3"} and o["order_id"] != "O-077"
    ]
    for order in rng.sample(candidates, 6):
        order["destination"] = rng.choice(europe)
        order["due"] = DUE_FIRST + timedelta(days=rng.randint(0, early_span))

    # Four tight P5 orders (B only) due in week 3: fine normally, but a capacity loss at B
    # makes some of them impossible.
    week3_start = PLANNING_START + timedelta(weeks=3)
    p5 = [o for o in orders if o["product"] == "P5"]
    for order in rng.sample(p5, 4):
        order["due"] = week3_start + timedelta(days=rng.randint(0, 6))
        order["qty"] = rng.choice([550, 560, 570, 580, 590, 600])
        order["destination"] = rng.choice(europe)

    return orders


def scale_capacity(plant_rows: list[dict], orders: list[dict]) -> float:
    """Scale every capacity by one common factor so demand is about TARGET_LOAD of
    four weeks of capacity. Returns the resulting load ratio."""
    demand = sum(o["qty"] for o in orders)
    base_rows = [r for r in plant_rows if r["week_start"] == ""]
    four_weeks = 4 * sum(r["weekly_capacity"] for r in base_rows)
    factor = demand / (TARGET_LOAD * four_weeks)
    for row in plant_rows:
        row["weekly_capacity"] = int(round(row["weekly_capacity"] * factor / 10.0) * 10)
    scaled = 4 * sum(r["weekly_capacity"] for r in base_rows)
    return demand / scaled


def write_csv(path: Path, columns: list[str], rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=columns, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({c: _fmt(row[c]) for c in columns})


def _fmt(value) -> str:
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, float):
        return f"{value:.2f}"
    return str(value)


def generate(out: Path, drop_out: Path, n_orders: int = N_ORDERS) -> dict:
    rng = random.Random(SEED)
    plants = make_plants(rng)
    transport = make_transport(rng)
    orders = make_orders(rng, n_orders)
    plants = add_dirty_week(plants)
    load = scale_capacity(plants, orders)

    write_csv(out / "plants.csv", PLANT_COLUMNS, plants)
    write_csv(out / "transport_duties.csv", TRANSPORT_COLUMNS, transport)
    write_csv(out / "orders.csv", ORDER_COLUMNS, orders)
    write_csv(out / "capacity_events.csv", EVENT_COLUMNS, [])
    counts = {
        "orders": len(orders),
        "plants": len(plants),
        "transport_duties": len(transport),
        "capacity_events": 0,
    }
    (out / "row_counts.json").write_text(json.dumps(counts, indent=2) + "\n", encoding="utf-8")

    for name, values in DROP_FILES.items():
        write_csv(drop_out / name, EVENT_COLUMNS, [dict(zip(EVENT_COLUMNS, values, strict=True))])

    return {"counts": counts, "load": load, "demand": sum(o["qty"] for o in orders)}


def _read_tables(out: Path) -> dict:
    import pandas as pd

    from app.db import to_date

    tables = {
        "orders": pd.read_csv(out / "orders.csv"),
        "plants": pd.read_csv(out / "plants.csv", keep_default_na=False),
        "transport_duties": pd.read_csv(out / "transport_duties.csv"),
    }
    tables["orders"]["due"] = pd.Series([to_date(v) for v in tables["orders"]["due"]], dtype=object)
    plants = tables["plants"]
    plants["week_start"] = pd.Series([to_date(v) for v in plants["week_start"]], dtype=object)
    plants["energy_price_per_kwh"] = pd.to_numeric(plants["energy_price_per_kwh"], errors="coerce")
    return tables


def check_traps(out: Path) -> list[tuple[str, str]]:
    """Assert the planted traps exist (spec 1.6), using the real cost model."""
    try:
        from app.config import Settings
        from app.core.costing import build_options, cheapest_option_per_order
    except ImportError:
        print("trap checks skipped: app.core.costing is not available")
        return []

    tables = _read_tables(out)
    settings = Settings(_env_file=None, planning_start=PLANNING_START)
    options = build_options(tables, PLANNING_START, 5, settings)
    cheapest = cheapest_option_per_order(options)
    by_order: dict[str, list] = {}
    for o in options:
        by_order.setdefault(o.order_id, []).append(o)
    orders = tables["orders"]

    assert len(orders) >= 100, "need at least 100 orders"
    assert orders["destination"].nunique() >= 8, "need at least 8 destinations"
    assert tables["plants"]["plant"].nunique() == 3, "need 3 plants"

    cheapest_late = sorted(
        oid
        for oid, best in cheapest.items()
        if best.days_late > 0 and any(o.on_time for o in by_order[oid])
    )
    assert len(cheapest_late) >= 3, f"only {len(cheapest_late)} cheapest-but-late orders"

    o77 = by_order["O-077"]
    a0 = next(o for o in o77 if o.plant == "A" and o.week == 0)
    c0 = next(o for o in o77 if o.plant == "C" and o.week == 0)
    assert cheapest["O-077"].plant == "A", "A must be cheapest for O-077"
    assert a0.days_late == 3, "A must be exactly 3 days late for O-077"
    assert c0.on_time, "C must be on time for O-077"

    probe = type("Probe", (), {})()
    probe.order_id, probe.product, probe.qty = "probe", "P1", 1
    probe.destination, probe.due = "USA", DUE_LAST
    from app.core.costing import Pricing

    pricing = Pricing(tables, PLANNING_START, settings)
    usa = {p: pricing.option(probe, p, 0).cost for p in ("A", "B", "C")}
    assert min(usa, key=usa.get) != "A", "A must not be the cheapest landed cost for P1 to USA"

    makers = tables["plants"].groupby("product")["plant"].nunique()
    single = sorted(makers[makers == 1].index)
    assert single, "need a product made at exactly one plant"

    found = [
        (
            "cheapest option late, on-time option exists",
            f"{len(cheapest_late)} orders, e.g. {', '.join(cheapest_late[:5])}",
        ),
        (
            "O-077",
            f"A cheapest, arrives {a0.arrival} ({a0.days_late} days late); C arrives {c0.arrival}, on time",
        ),
        ("duty trap P1 to USA", ", ".join(f"{p} {c:.2f}/unit" for p, c in usa.items())),
        (
            "single-plant products",
            ", ".join(
                f"{p} only at {tables['plants'].loc[tables['plants']['product'] == p, 'plant'].iloc[0]}"
                for p in single
            ),
        ),
        ("B dirty week", f"carbon {B_DIRTY_CARBON_KG_PER_KWH} kg/kWh from {B_DIRTY_WEEK_START}"),
    ]
    width = max(len(name) for name, _ in found)
    print("traps found:")
    for name, detail in found:
        print(f"  {name.ljust(width)}  {detail}")
    return found


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, default=ROOT / "data" / "sample")
    parser.add_argument("--drop-out", type=Path, default=ROOT / "data" / "drop")
    parser.add_argument(
        "--orders", type=int, default=N_ORDERS, help="number of orders (default 150)"
    )
    args = parser.parse_args(argv)

    summary = generate(args.out, args.drop_out, args.orders)
    counts = summary["counts"]
    print(
        f"wrote {counts['orders']} orders, {counts['plants']} plant rows, "
        f"{counts['transport_duties']} transport rows to {args.out}"
    )
    print(f"wrote {len(DROP_FILES)} capacity event files to {args.drop_out}")
    print(f"demand {summary['demand']} units = {summary['load']:.1%} of 4-week capacity")
    check_traps(args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
