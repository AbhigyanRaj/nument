"""Write three sample traces (allocation, scenario re-plan, infeasible) to docs/traces/.

python scripts/export_traces.py            # mock LLM, throwaway database
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

os.environ["DB_URL"] = f"sqlite:///{ROOT / 'data' / 'traces.db'}"
os.environ.setdefault("MOCK_LLM", "true")

REQUESTS = {
    "trace_allocation.json": ("Allocate this week's orders.", "base"),
    "trace_scenario.json": ("Plant B loses 30% capacity. Re-plan.", "base"),
    "trace_infeasible.json": ("Re-plan.", "capacity_events_severe.csv"),
}


def main() -> int:
    from app.agent.graph import run_request
    from app.core.loader import ingest_csv
    from app.db import init_db, load_tables

    db = ROOT / "data" / "traces.db"
    for suffix in ("", "-wal", "-shm"):
        Path(str(db) + suffix).unlink(missing_ok=True)
    init_db()
    for table in ("plants", "transport_duties", "orders", "capacity_events"):
        path = ROOT / "data" / "sample" / f"{table}.csv"
        ingest_csv(table, path.read_bytes(), str(path))

    out = ROOT / "docs" / "traces"
    out.mkdir(parents=True, exist_ok=True)
    for name, (request, setup) in REQUESTS.items():
        events = ROOT / (
            "data/sample/capacity_events.csv" if setup == "base" else f"data/drop/{setup}"
        )
        ingest_csv("capacity_events", events.read_bytes(), str(events))
        r = run_request(request)
        trace = {
            "run_id": r["run_id"],
            "request": request,
            "answer_type": r["answer_type"],
            "steps": r["meta"]["steps"],
            "llm_calls": r["meta"]["llm_calls"],
            "tokens": r["meta"]["tokens"],
            "latency_ms": r["meta"]["latency_ms"],
            "number_check": {
                "checked": r["meta"]["number_check"]["checked"],
                "matched": r["meta"]["number_check"]["matched"],
            },
            "data_used": {
                "rows": {k: len(v) for k, v in load_tables().items()},
                "planning_start": r["meta"]["planning_start"],
                "capacity_events_active": r["meta"]["events"],
            },
            "summary": r["summary"],
            "kpis": r["kpis"],
            "validator": r["validator"],
        }
        (out / name).write_text(json.dumps(trace, indent=2, default=str) + "\n", encoding="utf-8")
        print(f"{name}: {r['answer_type']}, {len(trace['steps'])} steps")
    for suffix in ("", "-wal", "-shm"):
        Path(str(db) + suffix).unlink(missing_ok=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
