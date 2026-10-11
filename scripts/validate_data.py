"""Run the six dataset checks on the data in the database. Exit code 0 if all pass, else 1.

python scripts/validate_data.py
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.dataset import validation_report  # noqa: E402
from app.db import init_db  # noqa: E402
from scripts._cli import print_validation  # noqa: E402


def main() -> int:
    init_db()
    report = validation_report()
    print_validation(report)
    passed = sum(c["ok"] for c in report["checks"])
    print(f"{passed} of {len(report['checks'])} checks passed")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
