# Small helpers that print neat text tables for the command-line scripts.

"""Plain-text table printing shared by the command-line scripts."""

from __future__ import annotations

from collections.abc import Sequence


def print_table(headers: Sequence[str], rows: Sequence[Sequence[object]]) -> None:
    cells = [[str(c) for c in headers]] + [[str(c) for c in row] for row in rows]
    widths = [max(len(row[i]) for row in cells) for i in range(len(headers))]
    for n, row in enumerate(cells):
        print("  ".join(cell.ljust(widths[i]) for i, cell in enumerate(row)).rstrip())
        if n == 0:
            print("  ".join("-" * w for w in widths))


def print_ingest(results: list[dict]) -> None:
    print_table(
        ["table", "status", "loaded", "rejected", "ignored columns"],
        [
            [
                r["table"],
                r["status"],
                r["rows_loaded"],
                r["rows_rejected"],
                ", ".join(r["ignored_columns"]) or "-",
            ]
            for r in results
        ],
    )
    for r in results:
        for error in r.get("errors", []):
            print(f"  {r['table']}: {error}")
        for reject in r["rejects"]:
            print(f"  {r['table']} row {reject['row']}: {reject['reason']}")


def print_validation(report: dict) -> None:
    print_table(
        ["check", "result", "detail"],
        [[c["id"], "PASS" if c["ok"] else "FAIL", c["detail"]] for c in report["checks"]],
    )
    print(f"planning start {report['planning_start']}")
    for name, unit in report["units"].items():
        if name in ("duty_pct", "capacity_loss_pct"):
            print(f"  {unit}")
