"""Scenario JSON: what-if changes applied on top of the loaded data.

Accepted keys:
    capacity_loss    [{plant, pct, from_date?, to_date?}]   missing dates mean the whole horizon
    ignore_events    bool   plan without the capacity_events table
    exclude_plants   [plant, ...]
    exclude_orders   [order_id, ...]
    only_orders      [order_id, ...]
    on_time_only     bool
    carbon_cut_pct   number
The short form {"plant": "B", "capacity_loss_pct": 30} is also accepted.
"""

from __future__ import annotations

from datetime import date


def _as_date(value) -> date | None:
    if value in (None, ""):
        return None
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value)[:10])


def _plant(value) -> str:
    text = str(value).strip().upper()
    return text.removeprefix("PLANT").strip(" _-") or text


def normalise_scenario(scenario: dict | None) -> dict:
    scenario = dict(scenario or {})
    losses = list(scenario.get("capacity_loss") or [])
    if "plant" in scenario and ("capacity_loss_pct" in scenario or "pct" in scenario):
        losses.append(
            {
                "plant": scenario["plant"],
                "pct": scenario.get("capacity_loss_pct", scenario.get("pct")),
                "from_date": scenario.get("from_date"),
                "to_date": scenario.get("to_date"),
            }
        )
    capacity_loss = [
        {
            "plant": _plant(item["plant"]),
            "pct": float(item["pct"]),
            "from_date": _as_date(item.get("from_date") or item.get("from")),
            "to_date": _as_date(item.get("to_date") or item.get("to")),
        }
        for item in losses
    ]
    only = scenario.get("only_orders")
    cut = scenario.get("carbon_cut_pct")
    return {
        "capacity_loss": capacity_loss,
        "ignore_events": bool(scenario.get("ignore_events", False)),
        "exclude_plants": sorted({_plant(p) for p in scenario.get("exclude_plants") or []}),
        "exclude_orders": sorted(set(scenario.get("exclude_orders") or [])),
        "only_orders": sorted(set(only)) if only else None,
        "on_time_only": bool(scenario.get("on_time_only", False)),
        "carbon_cut_pct": float(cut) if cut is not None else None,
    }


def scenario_json(scenario: dict) -> dict:
    """The normalised scenario with dates as ISO strings, ready for JSON."""
    out = dict(scenario)
    out["capacity_loss"] = [
        {
            **item,
            "from_date": item["from_date"].isoformat() if item["from_date"] else None,
            "to_date": item["to_date"].isoformat() if item["to_date"] else None,
        }
        for item in scenario["capacity_loss"]
    ]
    return out
