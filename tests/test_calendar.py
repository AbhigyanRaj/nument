from datetime import date

import pandas as pd

from app.config import Settings
from app.core.calendar import (
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
