"""Calendar rules: planning start, horizon, week arithmetic and percentage scales.

Weeks are numbered from 0, starting on the planning-start Monday.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import date, timedelta

import pandas as pd

MIN_WEEKS = 2
MAX_WEEKS = 12

# The plan starts on the Monday on or before (earliest due date - PLANNING_LEAD_DAYS).
# The implementation plan states 14 days, but its own worked example (orders due from
# 19 Oct, week 0 starting 12 Oct, O-077 three days late from Plant A) needs 7: with 14 the
# plan would start on 5 Oct and the "cheapest plant is late" trap would disappear.
PLANNING_LEAD_DAYS = 7


def monday_on_or_before(d: date) -> date:
    return d - timedelta(days=d.weekday())


def planning_start(orders: pd.DataFrame, settings) -> date:
    """PLANNING_START if set (snapped to its Monday), else derived from the earliest due date."""
    if settings.planning_start is not None:
        return monday_on_or_before(settings.planning_start)
    if orders.empty:
        return monday_on_or_before(date.today())
    earliest = min(orders["due"])
    return monday_on_or_before(earliest - timedelta(days=PLANNING_LEAD_DAYS))


def week_start(start: date, week: int) -> date:
    return start + timedelta(weeks=week)


def week_of(start: date, d: date) -> int:
    """Week index containing `d` (negative for dates before the planning start)."""
    return (d - start).days // 7


def horizon_weeks(orders: pd.DataFrame, start: date) -> int:
    """Week 0 up to the week holding the latest due date, plus one spare week (2 to 12)."""
    if orders.empty:
        return MIN_WEEKS
    last_due_week = week_of(start, max(orders["due"]))
    return max(MIN_WEEKS, min(MAX_WEEKS, last_due_week + 2))


def normalise_pct(x: float) -> float:
    """A single value: above 1 is a percentage, otherwise already a fraction."""
    return x / 100.0 if x > 1 else x


def pct_scale(values: Iterable[float]) -> str:
    """Decide a whole column's scale: "percent" if any value is above 1, else "fraction".

    Judging the column rather than each value avoids reading a 1% duty as 100% in a column
    that is clearly in percent."""
    return "percent" if any(v > 1 for v in values) else "fraction"


def to_fraction(value: float, scale: str) -> float:
    return value / 100.0 if scale == "percent" else value
