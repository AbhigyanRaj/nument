# Command-line tool: load CSV files into the database, then validate them.

"""Load CSV files into the database, then run the dataset checks.

python scripts/load_data.py --dir data/sample [--mode replace|append]
python scripts/load_data.py --file data/drop/capacity_events.csv --table capacity_events
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.core.loader import REQUIRED, ingest_csv  # noqa: E402
from app.dataset import validation_report  # noqa: E402
from app.db import init_db  # noqa: E402
from scripts._cli import print_ingest, print_validation  # noqa: E402

# Lanes and plants first so the orders that follow can be checked against them.
LOAD_ORDER = ("plants", "transport_duties", "orders", "capacity_events")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Load CSVs into the database and validate.")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--dir", type=Path, help="folder with plants.csv, orders.csv, ...")
    source.add_argument("--file", type=Path, help="a single CSV file (needs --table)")
    parser.add_argument("--table", choices=sorted(REQUIRED), help="target table for --file")
    parser.add_argument("--mode", choices=("replace", "append"), default="replace")
    args = parser.parse_args(argv)

    if args.file and not args.table:
        parser.error("--file needs --table")

    init_db()
    if args.dir:
        jobs = [(t, args.dir / f"{t}.csv") for t in LOAD_ORDER if (args.dir / f"{t}.csv").is_file()]
        if not jobs:
            parser.error(f"no table CSVs found in {args.dir}")
    else:
        jobs = [(args.table, args.file)]

    results = [
        ingest_csv(table, path.read_bytes(), str(path.resolve()), args.mode) for table, path in jobs
    ]
    print_ingest(results)
    print()
    report = validation_report()
    print_validation(report)

    failed = any(r["status"] == "error" for r in results) or not report["ok"]
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
