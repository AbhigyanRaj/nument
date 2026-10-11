from datetime import date

from sqlalchemy import text

from app.config import get_settings
from app.db import get_engine, get_session, load_tables
from app.models import CapacityEvent, Order, Plant


def test_tables_are_created_in_the_configured_database(fresh_db):
    url = get_settings().db_url
    assert url.endswith("fresh.db")
    with get_engine().connect() as conn:
        names = {row[0] for row in conn.execute(text("select name from sqlite_master"))}
    for table in (
        "orders",
        "plants",
        "transport_duties",
        "capacity_events",
        "ingest_log",
        "plan_runs",
        "plan_allocations",
        "agent_runs",
    ):
        assert table in names


def test_sqlite_runs_in_wal_mode(fresh_db):
    with get_engine().connect() as conn:
        assert conn.execute(text("pragma journal_mode")).scalar() == "wal"


def test_load_tables_returns_python_dates(fresh_db):
    with get_session() as session:
        session.add(
            Order(order_id="O-1", product="P1", qty=10, destination="UK", due=date(2026, 10, 20))
        )
        session.add(
            Plant(
                plant="A",
                product="P1",
                weekly_capacity=100,
                unit_cost=1.0,
                energy_kwh_per_unit=1.0,
                carbon_kg_per_kwh=0.5,
            )
        )
        session.add(
            CapacityEvent(
                event_id="E-1",
                plant="A",
                from_date=date(2026, 10, 19),
                to_date=date(2026, 10, 25),
                capacity_loss_pct=30,
            )
        )
        session.commit()

    tables = load_tables()
    assert set(tables) == {"orders", "plants", "transport_duties", "capacity_events"}
    assert tables["orders"].loc[0, "due"] == date(2026, 10, 20)
    assert tables["plants"].loc[0, "week_start"] is None
    assert "id" not in tables["plants"].columns
    assert tables["capacity_events"].loc[0, "to_date"] == date(2026, 10, 25)
    assert tables["transport_duties"].empty
