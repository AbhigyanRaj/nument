# Works out cost, carbon and arrival date for every order at every plant and week.
# These 'options' are what the solver chooses from.

"""Landed cost, carbon and delivery for every way an order could be made.

An option is one (order, plant, production week). Money is rounded to cents and carbon to
grams when an option is created, so every later sum (solver, checker, KPIs, text) uses the
same values.

Per unit, for an order made at a plant in a given week:
    energy_cost = energy_kwh_per_unit * energy_price_per_kwh
    goods       = unit_cost + energy_cost
    duty        = duty_rate * (goods + transport)        # CIF-style base: goods plus freight
    landed      = goods + transport + duty
    carbon_kg   = energy_kwh_per_unit * carbon_kg_per_kwh + transport carbon per unit
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta

import pandas as pd

from app.core.calendar import pct_scale, to_fraction, week_start


@dataclass(frozen=True)
class Option:
    order_id: str
    product: str
    qty: int
    destination: str
    due: date
    plant: str
    week: int
    production: float
    energy: float
    transport: float
    duty: float
    cost: float
    carbon_kg: float
    arrival: date
    days_late: int

    @property
    def on_time(self) -> bool:
        return self.days_late == 0


def plant_params(
    plants: pd.DataFrame, plant: str, product: str, wk_start: date, settings
) -> dict | None:
    """Parameters for making `product` at `plant` in the week starting `wk_start`.

    The undated row is the default (or the earliest dated row if none is undated). A row
    whose week_start falls inside the week overrides the carbon intensity, and the energy
    price when it gives one. A blank energy price uses DEFAULT_ENERGY_PRICE_PER_KWH."""
    rows = plants.loc[(plants["plant"] == plant) & (plants["product"] == product)]
    if rows.empty:
        return None
    undated = rows.loc[rows["week_start"].map(lambda d: d is None)]
    base = undated.iloc[0] if not undated.empty else rows.sort_values("week_start").iloc[0]
    params = {
        "weekly_capacity": int(base["weekly_capacity"]),
        "unit_cost": float(base["unit_cost"]),
        "energy_kwh_per_unit": float(base["energy_kwh_per_unit"]),
        "carbon_kg_per_kwh": float(base["carbon_kg_per_kwh"]),
        "energy_price_per_kwh": base["energy_price_per_kwh"],
    }
    wk_end = wk_start + timedelta(days=6)
    override = rows.loc[rows["week_start"].map(lambda d: d is not None and wk_start <= d <= wk_end)]
    if not override.empty:
        row = override.iloc[0]
        params["carbon_kg_per_kwh"] = float(row["carbon_kg_per_kwh"])
        if not pd.isna(row["energy_price_per_kwh"]):
            params["energy_price_per_kwh"] = row["energy_price_per_kwh"]
    price = params["energy_price_per_kwh"]
    params["energy_price_per_kwh"] = (
        settings.default_energy_price_per_kwh if price is None or pd.isna(price) else float(price)
    )
    return params


def price_option(
    order, plant: str, week: int, params: dict, lane, duty_rate: float, start: date, settings
) -> Option:
    """Cost, carbon and arrival of making `order` at `plant` in `week`."""
    qty = int(order.qty)
    energy_per_unit = params["energy_kwh_per_unit"] * params["energy_price_per_kwh"]
    goods_per_unit = params["unit_cost"] + energy_per_unit
    transport_per_unit = float(lane.transport_cost_per_unit)
    duty_per_unit = duty_rate * (goods_per_unit + transport_per_unit)
    landed_per_unit = goods_per_unit + transport_per_unit + duty_per_unit
    carbon_per_unit = params["energy_kwh_per_unit"] * params["carbon_kg_per_kwh"] + float(
        lane.carbon_kg_per_unit
    )
    ship = week_start(start, week) + timedelta(days=settings.ship_offset_days)
    arrival = ship + timedelta(days=int(lane.transit_days))
    return Option(
        order_id=order.order_id,
        product=order.product,
        qty=qty,
        destination=order.destination,
        due=order.due,
        plant=plant,
        week=week,
        production=round(qty * params["unit_cost"], 2),
        energy=round(qty * energy_per_unit, 2),
        transport=round(qty * transport_per_unit, 2),
        duty=round(qty * duty_per_unit, 2),
        cost=round(qty * landed_per_unit, 2),
        carbon_kg=round(qty * carbon_per_unit, 3),
        arrival=arrival,
        days_late=max(0, (arrival - order.due).days),
    )


class Pricing:
    """Lookups shared by build_options, the plan checker and explanations."""

    def __init__(self, tables: dict[str, pd.DataFrame], start: date, settings):
        self.plants = tables["plants"]
        self.start = start
        self.settings = settings
        lanes = tables["transport_duties"]
        self.lanes = {(r.plant, r.destination): r for r in lanes.itertuples()}
        self.duty_scale = pct_scale(list(lanes["duty_pct"]))
        self.makers: dict[str, set[str]] = defaultdict(set)
        for row in self.plants.itertuples():
            self.makers[row.product].add(row.plant)
        self._params: dict[tuple[str, str, int], dict | None] = {}

    def params(self, plant: str, product: str, week: int) -> dict | None:
        key = (plant, product, week)
        if key not in self._params:
            self._params[key] = plant_params(
                self.plants, plant, product, week_start(self.start, week), self.settings
            )
        return self._params[key]

    def eligible(self, plant: str, product: str, destination: str) -> bool:
        return plant in self.makers.get(product, ()) and (plant, destination) in self.lanes

    def option(self, order, plant: str, week: int) -> Option | None:
        if not self.eligible(plant, order.product, order.destination):
            return None
        lane = self.lanes[(plant, order.destination)]
        duty_rate = to_fraction(float(lane.duty_pct), self.duty_scale)
        params = self.params(plant, order.product, week)
        return price_option(order, plant, week, params, lane, duty_rate, self.start, self.settings)


def build_options(
    tables: dict[str, pd.DataFrame], start: date, n_weeks: int, settings
) -> list[Option]:
    """Every option: each order, at each plant that makes its product and has a lane to its
    destination, in each week of the horizon. Orders with no eligible plant get none."""
    orders = tables["orders"]
    if orders.empty or tables["plants"].empty:
        return []
    pricing = Pricing(tables, start, settings)
    options: list[Option] = []
    for order in orders.sort_values("order_id").itertuples():
        for plant in sorted(pricing.makers.get(order.product, ())):
            for week in range(n_weeks):
                option = pricing.option(order, plant, week)
                if option is not None:
                    options.append(option)
    return options


def cheapest_option_per_order(options: list[Option]) -> dict[str, Option]:
    """The lowest-cost option per order, ignoring capacity and lateness (ties: earlier week,
    then plant name)."""
    best: dict[str, Option] = {}
    for option in options:
        current = best.get(option.order_id)
        if current is None or (option.cost, option.week, option.plant) < (
            current.cost,
            current.week,
            current.plant,
        ):
            best[option.order_id] = option
    return best
