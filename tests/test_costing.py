from datetime import date

import pandas as pd
import pytest

from app.config import Settings
from app.core.costing import build_options, cheapest_option_per_order

START = date(2026, 10, 12)
SETTINGS = Settings(_env_file=None)


def _tiny(duty_pct=10.0, energy_price=0.1) -> dict:
    return {
        "orders": pd.DataFrame(
            [
                {
                    "order_id": "O-1",
                    "product": "P1",
                    "qty": 10,
                    "destination": "UK",
                    "due": date(2026, 10, 20),
                }
            ]
        ),
        "plants": pd.DataFrame(
            [
                {
                    "plant": "A",
                    "product": "P1",
                    "weekly_capacity": 100,
                    "unit_cost": 20.0,
                    "energy_kwh_per_unit": 4.0,
                    "carbon_kg_per_kwh": 0.5,
                    "energy_price_per_kwh": energy_price,
                    "week_start": None,
                }
            ]
        ),
        "transport_duties": pd.DataFrame(
            [
                {
                    "plant": "A",
                    "destination": "UK",
                    "transport_cost_per_unit": 2.0,
                    "transit_days": 3,
                    "duty_pct": duty_pct,
                    "carbon_kg_per_unit": 1.0,
                }
            ]
        ),
        "capacity_events": pd.DataFrame(),
    }


def test_hand_computed_example():
    # Per unit: 20 + 0.4 energy + 2 transport + 10% of 22.4 duty = 24.64.
    option = build_options(_tiny(), START, 2, SETTINGS)[0]
    assert option.cost == pytest.approx(246.40)
    assert (option.production, option.energy, option.transport, option.duty) == (
        200.0,
        4.0,
        20.0,
        22.4,
    )
    assert option.carbon_kg == pytest.approx(30.0)  # 10 * (4 * 0.5 + 1.0)


def test_duty_as_a_fraction_gives_the_same_cost():
    option = build_options(_tiny(duty_pct=0.10), START, 1, SETTINGS)[0]
    assert option.cost == pytest.approx(246.40)


def test_blank_energy_price_uses_the_default():
    option = build_options(_tiny(energy_price=None), START, 1, SETTINGS)[0]
    assert SETTINGS.default_energy_price_per_kwh == pytest.approx(0.10)
    assert option.energy == pytest.approx(4.0)


def test_arrival_is_friday_ship_plus_transit():
    week0, week1 = build_options(_tiny(), START, 2, SETTINGS)
    assert week0.arrival == date(2026, 10, 19)  # Fri 16 Oct + 3 days
    assert week0.on_time and week0.days_late == 0
    assert week1.arrival == date(2026, 10, 26)
    assert week1.days_late == 6


def test_missing_lane_means_no_option():
    tiny = _tiny()
    tiny["transport_duties"] = tiny["transport_duties"].iloc[0:0]
    assert build_options(tiny, START, 2, SETTINGS) == []


def test_o077_cheapest_plant_is_late(tables):
    options = [o for o in build_options(tables, START, 5, SETTINGS) if o.order_id == "O-077"]
    cheapest = cheapest_option_per_order(options)["O-077"]
    assert cheapest.plant == "A"
    a_week0 = next(o for o in options if o.plant == "A" and o.week == 0)
    c_week0 = next(o for o in options if o.plant == "C" and o.week == 0)
    assert a_week0.arrival == date(2026, 10, 30) and a_week0.days_late == 3
    assert c_week0.arrival == date(2026, 10, 21) and c_week0.on_time


def test_plant_b_dirty_week_raises_carbon(tables):
    options = build_options(tables, START, 5, SETTINGS)
    b = {o.week: o for o in options if o.order_id == "O-077" and o.plant == "B"}
    assert b[2].carbon_kg > b[1].carbon_kg  # week of 26 Oct: 0.70 instead of 0.45 kg/kWh
    assert b[2].cost == b[1].cost  # only carbon changes


def test_single_plant_products_get_one_plant(tables):
    options = build_options(tables, START, 5, SETTINGS)
    plants_for = {}
    for o in options:
        plants_for.setdefault(o.product, set()).add(o.plant)
    assert plants_for["P4"] == {"A"}
    assert plants_for["P5"] == {"B"}
    assert plants_for["P1"] == {"A", "B", "C"}
