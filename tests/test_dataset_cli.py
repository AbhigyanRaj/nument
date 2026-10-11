import re
import shutil

from app.core.loader import ingest_csv
from app.dataset import expected_counts, validation_report
from scripts import load_data, validate_data


def test_sample_data_validates_against_its_card(sample_db):
    report = validation_report()
    assert report["ok"], report["checks"]
    assert report["planning_start"] == "2026-10-12"
    assert report["checks"][5]["detail"].startswith("counts match the data card")


def test_a_late_drop_only_changes_its_own_table(fresh_db, sample_dir):
    for table in ("plants", "transport_duties", "orders", "capacity_events"):
        path = sample_dir / "sample" / f"{table}.csv"
        ingest_csv(table, path.read_bytes(), str(path))
    drop = sample_dir / "drop" / "capacity_events.csv"
    ingest_csv("capacity_events", drop.read_bytes(), str(drop))
    counts = expected_counts()
    assert counts == {"orders": 150, "plants": 15, "transport_duties": 36}
    assert validation_report()["ok"]


def test_uploads_have_no_data_card(fresh_db, sample_dir):
    for table in ("plants", "transport_duties", "orders"):
        path = sample_dir / "sample" / f"{table}.csv"
        ingest_csv(table, path.read_bytes(), f"{table}.csv")  # an upload: bare file name
    assert expected_counts() is None
    v6 = validation_report()["checks"][5]
    assert v6["ok"] and v6["detail"].startswith("no data card")


def test_cli_loads_a_folder_and_validates(fresh_db, sample_dir, tmp_path, capsys):
    folder = tmp_path / "upload"
    shutil.copytree(sample_dir / "sample", folder)
    assert load_data.main(["--dir", str(folder)]) == 0
    out = capsys.readouterr().out
    assert re.search(r"^orders\s+ok\s+150\s+0\s", out, re.MULTILINE)
    assert out.count("PASS") == 6

    assert validate_data.main() == 0
    assert "6 of 6 checks passed" in capsys.readouterr().out


def test_cli_single_file_needs_a_table(fresh_db, sample_dir, capsys):
    drop = sample_dir / "drop" / "capacity_events_severe.csv"
    try:
        load_data.main(["--file", str(drop)])
    except SystemExit as exc:
        assert exc.code == 2
    assert "--file needs --table" in capsys.readouterr().err
