# Tests that the generated dataset is identical every time it is created.

"""The synthetic dataset must regenerate byte for byte, and match what is committed."""

from pathlib import Path

from scripts.generate_data import generate

ROOT = Path(__file__).resolve().parents[1]


def _files(folder: Path) -> dict[str, bytes]:
    return {p.name: p.read_bytes() for p in sorted(folder.iterdir()) if p.name != ".gitkeep"}


def test_generator_is_deterministic(tmp_path):
    generate(tmp_path / "a" / "sample", tmp_path / "a" / "drop")
    generate(tmp_path / "b" / "sample", tmp_path / "b" / "drop")
    assert _files(tmp_path / "a" / "sample") == _files(tmp_path / "b" / "sample")
    assert _files(tmp_path / "a" / "drop") == _files(tmp_path / "b" / "drop")


def test_committed_data_matches_the_generator(tmp_path):
    generate(tmp_path / "sample", tmp_path / "drop")
    assert _files(ROOT / "data" / "sample") == _files(tmp_path / "sample")
    assert _files(ROOT / "data" / "drop") == _files(tmp_path / "drop")


def test_row_counts_and_traps_are_present(tmp_path):
    summary = generate(tmp_path / "sample", tmp_path / "drop")
    assert summary["counts"] == {
        "orders": 150,
        "plants": 15,
        "transport_duties": 36,
        "capacity_events": 0,
    }
    assert 0.70 <= summary["load"] <= 0.78
    orders = (tmp_path / "sample" / "orders.csv").read_text().splitlines()
    assert "O-077,P1,500,Germany,2026-10-27" in orders
    transport = (tmp_path / "sample" / "transport_duties.csv").read_text().splitlines()
    assert any(line.startswith("A,USA,") and line.split(",")[4] == "28" for line in transport)
