from datetime import date

import pandas as pd

from app.config import Settings
from app.core.calendar import (
    base_capacity,
    effective_capacity,
    horizon_weeks,
    monday_on_or_before,
    normalise_pct,
    pct_scale,
    planning_start,
    to_fraction,
    week_of,
    week_start,
)


def _orders(*dues: str) -> pd.DataFrame:
    return pd.DataFrame({"due": [date.fromisoformat(d) for d in dues]})


def _settings(**kw) -> Settings:
    return Settings(_env_file=None, **kw)


def test_monday_on_or_before():
    assert monday_on_or_before(date(2026, 10, 12)) == date(2026, 10, 12)  # Monday
    assert monday_on_or_before(date(2026, 10, 18)) == date(2026, 10, 12)  # Sunday
    assert monday_on_or_before(date(2026, 10, 19)) == date(2026, 10, 19)


def test_planning_start_matches_the_worked_example():
    # Earliest due 19 Oct -> plan starts Monday 12 Oct, so A's Friday-16-Oct shipment
    # of O-077 arrives 30 Oct, three days late.
    start = planning_start(_orders("2026-10-27", "2026-10-19", "2026-11-08"), _settings())
    assert start == date(2026, 10, 12)


def test_planning_start_from_settings_is_snapped_to_monday():
    s = _settings(planning_start=date(2026, 10, 14))
    assert planning_start(_orders("2026-10-27"), s) == date(2026, 10, 12)


def test_horizon_covers_latest_due_week_plus_one():
    start = date(2026, 10, 12)
    assert horizon_weeks(_orders("2026-10-19", "2026-11-08"), start) == 5  # weeks 0-4
    assert horizon_weeks(_orders("2026-10-13"), start) == 2  # clamped up
    assert horizon_weeks(_orders("2027-06-01"), start) == 12  # clamped down


def test_week_arithmetic_round_trips():
    start = date(2026, 10, 12)
    assert week_start(start, 3) == date(2026, 11, 2)
    assert week_of(start, date(2026, 11, 8)) == 3
    assert week_of(start, date(2026, 10, 11)) == -1


def test_percent_scales():
    assert normalise_pct(30) == 0.30
    assert normalise_pct(0.3) == 0.3
    assert pct_scale([0, 4, 28]) == "percent"
    assert pct_scale([0.0, 0.04]) == "fraction"
    assert to_fraction(4, "percent") == 0.04
    assert to_fraction(0.04, "fraction") == 0.04


def _plants(*rows) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"plant": p, "product": prod, "weekly_capacity": cap, "week_start": ws}
            for p, prod, cap, ws in rows
        ]
    )


def test_capacity_events_reduce_overlapping_weeks():
    start = date(2026, 10, 12)
    plants = _plants(("B", "P1", 1500, None), ("A", "P1", 2000, None))
    event = {
        "plant": "B",
        "from_date": date(2026, 10, 19),
        "to_date": date(2026, 11, 1),
        "loss": 0.3,
    }
    cap = effective_capacity(plants, [event], start, 5)
    assert cap[("B", "P1", 0)] == 1500
    assert cap[("B", "P1", 1)] == 1050  # not 1049: floating point must not eat a unit
    assert cap[("B", "P1", 2)] == 1050
    assert cap[("B", "P1", 3)] == 1500
    assert cap[("A", "P1", 1)] == 2000  # other plants untouched


def test_partial_weeks_and_stacked_events():
    start = date(2026, 10, 12)
    plants = _plants(("B", "P1", 700, None))
    events = [
        {"plant": "B", "from_date": date(2026, 10, 15), "to_date": date(2026, 10, 18), "loss": 0.7},
        {"plant": "B", "from_date": date(2026, 10, 12), "to_date": date(2026, 10, 18), "loss": 0.9},
    ]
    cap = effective_capacity(plants, events, start, 2)
    assert cap[("B", "P1", 0)] == 0  # 0.4 + 0.9 is capped at a full loss
    assert cap[("B", "P1", 1)] == 700


def test_base_capacity_uses_default_rows_and_falls_back_to_earliest_dated():
    start = date(2026, 10, 12)
    plants = _plants(
        ("A", "P1", 2000, None),
        ("A", "P1", 9999, date(2026, 10, 26)),  # a carbon override row: capacity ignored
        ("C", "P2", 500, date(2026, 11, 2)),
        ("C", "P2", 400, date(2026, 10, 19)),  # only dated rows: earliest is the default
    )
    cap = base_capacity(plants, start, 3)
    assert cap[("A", "P1", 2)] == 2000
    assert cap[("C", "P2", 0)] == 400
