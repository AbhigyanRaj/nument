# Data card: oa-synth v1

| Field | Value |
|---|---|
| Name and version | **oa-synth v1** |
| Date | 2026-10-11 |
| How it was made | `scripts/generate_data.py`, Python's `random.Random(42)`; no LLM was used to make any of the data |
| Reproduce | `python scripts/generate_data.py` (rewrites `data/sample` and `data/drop` byte for byte; `tests/test_determinism.py` enforces this) |
| Privacy | Fully synthetic. No real company, customer, supplier or personal data. Destinations are country names only. |

## Contents

| Table | Rows | Columns |
|---|---|---|
| `orders.csv` | 150 | `order_id, product, qty, destination, due` |
| `plants.csv` | 15 (11 default rows + 4 weekly overrides) | `plant, product, weekly_capacity, unit_cost, energy_kwh_per_unit, carbon_kg_per_kwh, energy_price_per_kwh, week_start` |
| `transport_duties.csv` | 36 (3 plants × 12 destinations) | `plant, destination, transport_cost_per_unit, transit_days, duty_pct, carbon_kg_per_unit` |
| `capacity_events.csv` | 0 (header only; events arrive as late data drops) | `event_id, plant, from_date, to_date, capacity_loss_pct` |
| `row_counts.json` | — | expected row counts, read by validation check V6 |

**Units.** `weekly_capacity` is units per week per (plant, product). Costs are per unit in one
unnamed currency. `energy_kwh_per_unit` is kWh per unit; `carbon_kg_per_kwh` is kg CO2e per kWh;
transport `carbon_kg_per_unit` is kg CO2e per unit. `duty_pct` and `capacity_loss_pct` are
percentages (0-100).

**Dates.** Planning starts Monday 2026-10-12 (week 0). Due dates run from 2026-10-19 to
2026-11-08 (weeks 1-3); the planning horizon is weeks 0-4.

**Orders.** 150 orders, `O-001` to `O-150`. Product mix P1 45, P2 37, P3 38, P4 15, P5 15.
Quantities 50-600 in steps of 10 (48,650 units in total). 12 destinations.

**Plants.**

| Plant | Character | Unit cost | Grid carbon (kg/kWh) | Energy price | Makes |
|---|---|---|---|---|---|
| A | cheapest, dirtiest, large | 20.15-24.06 | 0.82 | 0.08 | P1, P2, P3, P4 |
| B | middle | 24.18-27.27 | 0.45 (0.70 in the week of 26 Oct) | 0.11 | P1, P2, P3, P5 |
| C | dearest, greenest, small | 28.04-32.19 | 0.12 | 0.14 | P1, P2, P3 |

**Lanes.** Each plant has a home region: A near India, UAE and Singapore; B near Germany, France
and the UK; C near the USA, Mexico and Brazil. Near lanes cost 1.0-2.0 per unit, take 2-4 days
and carry no duty; medium lanes cost 2.0-3.5 and take 5-8 days; far lanes cost 3.5-6.0 and take
9-16 days. Off-region lanes carry 3-8% duty.

**Capacity.** Demand is 70.1% of total four-week capacity after one common scaling factor.

## Planted traps

| Trap | Where |
|---|---|
| Single-plant products | P4 is made only at A; P5 only at B |
| Weekly carbon change | Plant B's grid rises from 0.45 to 0.70 kg/kWh for the week of 2026-10-26 (override rows) |
| Duty trap | A to USA carries 28% duty, so A's low unit cost becomes a dear landed cost for US orders |
| Worked example | `O-077`: P1, 500 units to Germany, due 2026-10-27. A is cheapest but ships 16 Oct + 14 days = 30 Oct, three days late; C ships the same day + 5 days = 21 Oct, on time |
| Cheapest is late | Six more P1-P3 orders to Germany, France or the UK due 19-28 Oct, where far-away A is cheap but slow |
| Tight P5 orders | Four large P5 orders due in week 3; fine normally, but a capacity loss at B makes some impossible |
| Late data drops | `data/drop/capacity_events.csv` (B -30%, 19 Oct-1 Nov), `capacity_events_severe.csv` (B -85%, 19 Oct-8 Nov: leaves P5 orders unmet), `capacity_events_A.csv` (A -50%, 12-25 Oct) |

## Deviation from the implementation plan

The plan suggests weekly capacities of 900 for A·P4 and 700 for B·P5. Because P4 and P5 each carry
10% of demand, those values put them at 157% and 212% of four-week capacity, so even the default
plan and the plan's own "B loses 30%" and "A loses 50%" re-plan cases would be infeasible. The
generator raises them to 3,200 and 2,300 before the common scaling, with a target load of 70% (the
plan allows 70-78%). After scaling, the 30% and 50% whole-horizon losses keep 17% and 20%
headroom, while the severe B event still leaves P5 short, as intended.

## Checks run

`python scripts/load_data.py --dir data/sample` followed by `python scripts/validate_data.py`:

```
check  result  detail
-----  ------  -------------------------------------------------------------------------------------------
V1     PASS    all 150 orders have at least one plant that makes their product
V2     PASS    all 36 plant-destination pairs have a transport row
V3     PASS    all 15 rows positive, 580 to 2,670 units per week
V4     PASS    all due dates are after the planning start 2026-10-12
V5     PASS    grid 0.12 to 0.82 kg CO2e per kWh (allowed 0 to 2); transport 0.35 to 2.35 kg CO2e per unit
V6     PASS    counts match the data card: orders 150, plants 15, transport_duties 36, capacity_events 0
planning start 2026-10-12
  duty_pct: read as percent (values above 1 found)
  capacity_loss_pct: no rows yet
6 of 6 checks passed
```

The generator's trap assertions are added when the cost model lands.

## Known limits

- No order splitting: an order is produced whole, in one week, at one plant.
- Duty rates are constant for the period; one ship day per week (Friday); transit days are fixed.
- Inventory, changeovers and transport capacity are not modelled.
- The economics are illustrative and not calibrated to any real market.
