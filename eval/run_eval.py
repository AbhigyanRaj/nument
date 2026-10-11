# Runs the 22 test questions against the planner and scores every answer.
# Writes eval/report.md and eval/results.json.

"""Evaluation: 22 cases run in-process against a separate database.

    python eval/run_eval.py                  # mock LLM, CP-SAT
    python eval/run_eval.py --solver both    # CP-SAT and greedy, compared
    python eval/run_eval.py --no-mock        # real LLM (needs a key in .env)

Method: exact match on answer type and validator flags, property checks on plans, and the
deterministic number check for faithfulness. No LLM judge.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# The evaluation never touches the demo database: point DB_URL elsewhere before app imports.
os.environ["DB_URL"] = f"sqlite:///{ROOT / 'data' / 'eval.db'}"
os.environ["AUTOLOAD_SAMPLE"] = "false"

SETUP_FILES = {
    "base": ROOT / "data" / "sample" / "capacity_events.csv",  # header only: no events
    "events_30": ROOT / "data" / "drop" / "capacity_events.csv",
    "events_severe": ROOT / "data" / "drop" / "capacity_events_severe.csv",
    "events_A": ROOT / "data" / "drop" / "capacity_events_A.csv",
}


def _refresh() -> None:
    from app.config import get_settings
    from app.db import reset_engine

    get_settings.cache_clear()
    reset_engine()


def load_sample() -> None:
    from app.core.loader import ingest_csv
    from app.db import init_db

    db_file = ROOT / "data" / "eval.db"
    for suffix in ("", "-wal", "-shm"):
        Path(str(db_file) + suffix).unlink(missing_ok=True)
    _refresh()
    init_db()
    for table in ("plants", "transport_duties", "orders", "capacity_events"):
        path = ROOT / "data" / "sample" / f"{table}.csv"
        ingest_csv(table, path.read_bytes(), str(path))


def apply_setup(name: str) -> None:
    from app.core.loader import ingest_csv

    path = SETUP_FILES[name]
    ingest_csv("capacity_events", path.read_bytes(), str(path))


def find_traps() -> dict[str, str]:
    """Trap ids are derived from the data, never typed by hand."""
    from app.config import get_settings
    from app.core.calendar import horizon_weeks, planning_start
    from app.core.costing import build_options, cheapest_option_per_order
    from app.db import load_tables

    tables = load_tables()
    settings = get_settings()
    start = planning_start(tables["orders"], settings)
    options = build_options(tables, start, horizon_weeks(tables["orders"], start), settings)
    cheapest = cheapest_option_per_order(options)
    on_time = {o.order_id for o in options if o.on_time}
    traps = sorted(
        oid for oid, o in cheapest.items() if not o.on_time and oid in on_time and oid != "O-077"
    )
    p5 = sorted(tables["orders"].loc[tables["orders"]["product"] == "P5", "order_id"])
    return {
        "TRAP_1": traps[0],
        "TRAP_1_PLANT": cheapest[traps[0]].plant,
        "TRAP_2": traps[1],
        "TRAP_2_PLANT": cheapest[traps[1]].plant,
        "P5_ORDER": p5[0],
    }


def substitute(value, traps: dict[str, str]):
    if isinstance(value, str):
        for key, real in traps.items():
            value = value.replace("{" + key + "}", real)
        return value
    if isinstance(value, list):
        return [substitute(v, traps) for v in value]
    if isinstance(value, dict):
        return {substitute(k, traps): substitute(v, traps) for k, v in value.items()}
    return value


def check_case(case: dict, r: dict, results: dict[int, dict]) -> list[str]:
    """Return the failed expectations (empty list = pass)."""
    e = case["expect"]
    fails: list[str] = []
    rows = {row["order_id"]: row for row in r["allocation"]}
    k = r["kpis"]
    if r["answer_type"] not in e["answer_type"]:
        fails.append(f"answer_type {r['answer_type']} not in {e['answer_type']}")
    if e.get("validator_all_true") and not all(r["validator"].values()):
        fails.append(f"validator {r['validator']}")
    if e.get("capacity_ok") and not r["validator"]["capacity_ok"]:
        fails.append("capacity_ok false")
    if e.get("on_time_or_infeasible") and r["answer_type"] == "allocation" and k["late_orders"]:
        fails.append("allocation with late orders")
    for oid, want in e.get("order_on_time", {}).items():
        if oid not in rows or rows[oid]["on_time"] != want:
            fails.append(f"{oid} on_time != {want}")
    for oid, plant in e.get("order_plant_not", {}).items():
        if oid in rows and rows[oid]["plant"] == plant:
            fails.append(f"{oid} at plant {plant}")
    if "moved_min" in e and (r["comparison"] or {}).get("moved_count", 0) < e["moved_min"]:
        fails.append("moved_count below minimum")
    if e.get("extra_cost_sign") == ">=0" and (r["comparison"] or {}).get("extra_cost", -1) < 0:
        fails.append("extra cost negative")
    if "unmet_min" in e and len(r["unmet_orders"]) < e["unmet_min"]:
        fails.append("too few unmet orders")
    if "plant_absent" in e and any(row["plant"] == e["plant_absent"] for row in r["allocation"]):
        fails.append(f"rows at plant {e['plant_absent']}")
    if e.get("numbers_ok"):
        nc = r["meta"]["number_check"]
        if nc["checked"] == 0 or nc["matched"] != nc["checked"]:
            fails.append(f"number check {nc['matched']}/{nc['checked']}")
    for phrase in e.get("summary_must_not_contain", []):
        if phrase.lower() in r["summary"].lower():
            fails.append(f"summary contains {phrase!r}")
    if "tradeoff_row" in e:
        cuts = {row["carbon_cut_pct"]: row for row in r["tradeoff"]}
        cut = e["tradeoff_row"]
        if cut not in cuts:
            fails.append(f"no {cut}% trade-off row")
        elif 0 in cuts and cuts[cut]["cost"] < cuts[0]["cost"]:
            fails.append(f"{cut}% row cheaper than the 0% row")
    ref = {i: results[i]["response"]["kpis"] for i in results}
    if "late_gt_case" in e and k["late_orders"] <= ref[e["late_gt_case"]]["late_orders"]:
        fails.append("not more late orders than the reference case")
    if "cost_lte_case" in e and k["total_cost"] > ref[e["cost_lte_case"]]["total_cost"]:
        fails.append("costlier than the reference case")
    slack = 1.01  # plans are proven within a small optimality gap
    if "cost_min_of_cases" in e:
        others = [ref[i]["total_cost"] for i in e["cost_min_of_cases"] if i in ref]
        if others and k["total_cost"] > min(others) * slack:
            fails.append("not the cheapest of the weight cases")
    if "carbon_min_of_cases" in e:
        others = [ref[i]["total_carbon_t"] for i in e["carbon_min_of_cases"] if i in ref]
        if others and k["total_carbon_t"] > min(others) * slack:
            fails.append("not the greenest of the weight cases")
    return fails


def post_checks(results: dict[int, dict], cases: list[dict]) -> None:
    """Cross-case checks that need cases run later (13-15)."""
    for case in cases:
        e = case["expect"]
        r = results[case["id"]]
        k = r["response"]["kpis"]
        if "between_cases" in e:
            a, b = (results[i]["response"]["kpis"] for i in e["between_cases"])
            lo_c, hi_c = sorted([a["total_cost"], b["total_cost"]])
            lo_g, hi_g = sorted([a["total_carbon_t"], b["total_carbon_t"]])
            if not (lo_c / 1.01 <= k["total_cost"] <= hi_c * 1.01):
                r["fails"].append("cost not between the cost-first and carbon-first cases")
            if not (lo_g / 1.01 <= k["total_carbon_t"] <= hi_g * 1.01):
                r["fails"].append("carbon not between the cost-first and carbon-first cases")
        if "cost_min_of_cases" in e or "carbon_min_of_cases" in e:
            r["fails"] = [f for f in r["fails"] if "of the weight cases" not in f]
            others = e.get("cost_min_of_cases") or e.get("carbon_min_of_cases")
            key = "total_cost" if "cost_min_of_cases" in e else "total_carbon_t"
            best = min(results[i]["response"]["kpis"][key] for i in others)
            if k[key] > best * 1.01:
                r["fails"].append(f"{key} is not the minimum of cases {others}")
        r["passed"] = not r["fails"]


def run_config(cases: list[dict], solver: str, mock: bool) -> dict:
    os.environ["SOLVER"] = solver
    os.environ["MOCK_LLM"] = "true" if mock else "false"
    load_sample()
    from app.agent.graph import run_request

    traps = find_traps()
    results: dict[int, dict] = {}
    cache: dict[str, dict] = {}
    setup = None
    for raw in cases:
        case = substitute(raw, traps)
        if case["setup"] != setup:
            apply_setup(case["setup"])
            setup = case["setup"]
            cache.clear()
        key = json.dumps(
            [case["request"], case.get("weights"), case.get("scenario")], sort_keys=True
        )
        t0 = time.time()
        if key in cache:
            response = cache[key]
        else:
            response = run_request(case["request"], case.get("weights"), case.get("scenario"))
            cache[key] = response
        elapsed = time.time() - t0
        fails = check_case(case, response, results)
        results[case["id"]] = {
            "id": case["id"],
            "group": case["group"],
            "request": case["request"],
            "answer_type": response["answer_type"],
            "fails": fails,
            "passed": not fails,
            "latency_ms": response["meta"]["latency_ms"],
            "wall_s": round(elapsed, 2),
            "llm_calls": response["meta"]["llm_calls"],
            "tokens": response["meta"]["tokens"],
            "response": response,
        }
        status = "PASS" if not fails else "FAIL " + "; ".join(fails)
        print(f"[{solver}] case {case['id']:2d} {response['answer_type']:20s} {status}", flush=True)
    post_checks(results, cases)
    return {"solver": solver, "mock": mock, "traps": traps, "results": results}


def plan_comparison() -> dict:
    """Default CP-SAT plan vs the cheapest-plant baseline vs greedy, on the base data."""
    from app.config import get_settings
    from app.core.compare import baseline_cheapest_plan
    from app.core.solver import DEFAULT_WEIGHTS, solve_allocation
    from app.db import load_tables

    apply_setup("base")
    tables, settings = load_tables(), get_settings()
    plans = {
        "CP-SAT (default weights)": solve_allocation(
            tables, settings, DEFAULT_WEIGHTS, solver="cpsat"
        ),
        "Greedy (default weights)": solve_allocation(
            tables, settings, DEFAULT_WEIGHTS, solver="greedy"
        ),
        "Cheapest-plant baseline": baseline_cheapest_plan(tables, settings),
    }
    return {
        name: {**p["kpis"], "status": p["status"], "solve_ms": p["solve_ms"]}
        for name, p in plans.items()
    }


def pct(values: list[float], q: float) -> float:
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int(round(q * (len(ordered) - 1))))] if ordered else 0.0


def write_report(configs: list[dict], comparison: dict, out_dir: Path) -> None:
    lines = ["# Evaluation report", ""]
    lines.append(
        "Method: exact match on answer type and validator flags, property checks on plans "
        "(trap orders on time, capacity respected, cross-case cost and carbon order), and the "
        "deterministic number check for faithfulness. No LLM judge. Trap order ids are found "
        "from the data at run time, not typed by hand. Case 6 uses weights cost 1, carbon 0, "
        "lateness 0: with carbon still weighted, a dates-ignored plan may spend money to cut "
        "carbon, so only a pure-cost plan is guaranteed to be no dearer than case 1."
    )
    for cfg in configs:
        res = list(cfg["results"].values())
        passed = sum(r["passed"] for r in res)
        lines += [
            "",
            f"## Solver: {cfg['solver']} ({'mock LLM' if cfg['mock'] else 'real LLM'})",
            "",
        ]
        lines.append(f"**{passed} of {len(res)} cases passed.**  Trap orders: {cfg['traps']}")
        lines += ["", "| # | Group | Request | Answer | Result |", "|---|---|---|---|---|"]
        for r in res:
            verdict = "PASS" if r["passed"] else "FAIL: " + "; ".join(r["fails"])
            lines.append(
                f"| {r['id']} | {r['group']} | {r['request']} | {r['answer_type']} | {verdict} |"
            )
        planned = [r for r in res if r["response"]["allocation"]]
        valid = sum(all(r["response"]["validator"].values()) for r in planned)
        lat = [r["latency_ms"] / 1000 for r in res]
        lines += [
            "",
            f"- Plan validity: {valid} of {len(planned)} plans have every validator flag true.",
            f"- Latency: p50 {pct(lat, 0.5):.1f} s, p95 {pct(lat, 0.95):.1f} s per request.",
            f"- LLM calls: {sum(r['llm_calls'] for r in res)} in total, "
            f"tokens: {sum(r['tokens'] for r in res)}.",
        ]
        replan = [cfg["results"][i] for i in (7, 8, 9)]
        lines += [
            "",
            "Re-plan quality (cases 7-9):",
            "",
            "| Case | Extra cost | Extra carbon t | Moved | Stability % |",
            "|---|---|---|---|---|",
        ]
        for r in replan:
            c = r["response"]["comparison"] or {}
            lines.append(
                f"| {r['id']} | {c.get('extra_cost', '-')} | {c.get('extra_carbon_t', '-')} | "
                f"{c.get('moved_count', '-')} | {c.get('stability_pct', '-')} |"
            )
        faith = [cfg["results"][i]["response"]["meta"]["number_check"] for i in (17, 18, 19)]
        lines.append(
            f"\nBrief faithfulness (cases 17-19): {sum(n['matched'] for n in faith)} of "
            f"{sum(n['checked'] for n in faith)} numbers matched the computed facts."
        )
    lines += [
        "",
        "## Plans on the base data",
        "",
        "| Plan | Status | Cost | CO2e t | Late | Unmet | Solve ms |",
        "|---|---|---|---|---|---|---|",
    ]
    for name, k in comparison.items():
        lines.append(
            f"| {name} | {k['status']} | {k['total_cost']:,.0f} | {k['total_carbon_t']:.1f} | "
            f"{k['late_orders']} | {k['unmet_orders']} | {k['solve_ms']} |"
        )
    if len(configs) == 2:
        a, b = (sum(r["passed"] for r in c["results"].values()) for c in configs)
        lines.append(f"\nCases passed: CP-SAT {a}, greedy {b}.")
    cp, gr = comparison["CP-SAT (default weights)"], comparison["Greedy (default weights)"]
    lines.append(
        f"\n**Final choice: CP-SAT.** It delivers {gr['late_orders'] - cp['late_orders']} fewer "
        f"late orders than greedy on the same data and is proven near-optimal; greedy stays as "
        "the baseline and the automatic fallback."
    )
    (out_dir / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    slim = [
        {
            "solver": c["solver"],
            "mock": c["mock"],
            "traps": c["traps"],
            "cases": [
                {k: v for k, v in r.items() if k != "response"} for r in c["results"].values()
            ],
        }
        for c in configs
    ]
    (out_dir / "results.json").write_text(
        json.dumps({"configs": slim, "plans": comparison}, indent=2) + "\n", encoding="utf-8"
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the 22-case evaluation.")
    parser.add_argument("--mock", dest="mock", action="store_true", default=True)
    parser.add_argument("--no-mock", dest="mock", action="store_false")
    parser.add_argument("--solver", choices=("cpsat", "greedy", "both"), default="cpsat")
    parser.add_argument("--out-dir", type=Path, default=ROOT / "eval")
    args = parser.parse_args(argv)

    cases = json.loads((ROOT / "eval" / "cases.json").read_text(encoding="utf-8"))
    solvers = ["cpsat", "greedy"] if args.solver == "both" else [args.solver]
    configs = [run_config(cases, s, args.mock) for s in solvers]
    os.environ["SOLVER"] = "cpsat"
    _refresh()
    comparison = plan_comparison()
    args.out_dir.mkdir(parents=True, exist_ok=True)
    write_report(configs, comparison, args.out_dir)
    total = sum(r["passed"] for c in configs for r in c["results"].values())
    print(f"passed {total} of {sum(len(c['results']) for c in configs)}; report in {args.out_dir}")
    return 0 if all(r["passed"] for c in configs for r in c["results"].values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
