"""The eight SQLModel tables: four input tables, the ingest log, and plan and agent records."""

from datetime import UTC, date, datetime

from sqlmodel import Field, SQLModel


def utcnow() -> datetime:
    return datetime.now(UTC)


# --- Input data ---------------------------------------------------------------------------


class Order(SQLModel, table=True):
    __tablename__ = "orders"

    order_id: str = Field(primary_key=True)
    product: str
    qty: int
    destination: str
    due: date


class Plant(SQLModel, table=True):
    """One row per (plant, product). A row with `week_start` set overrides the default row's
    carbon intensity (and energy price, if given) for the week containing that date."""

    __tablename__ = "plants"

    id: int | None = Field(default=None, primary_key=True)
    plant: str = Field(index=True)
    product: str
    weekly_capacity: int
    unit_cost: float
    energy_kwh_per_unit: float
    carbon_kg_per_kwh: float
    energy_price_per_kwh: float | None = None
    week_start: date | None = None


class TransportDuty(SQLModel, table=True):
    __tablename__ = "transport_duties"

    id: int | None = Field(default=None, primary_key=True)
    plant: str = Field(index=True)
    destination: str
    transport_cost_per_unit: float
    transit_days: int
    duty_pct: float
    carbon_kg_per_unit: float


class CapacityEvent(SQLModel, table=True):
    __tablename__ = "capacity_events"

    event_id: str = Field(primary_key=True)
    plant: str
    from_date: date
    to_date: date
    capacity_loss_pct: float


# --- Bookkeeping ---------------------------------------------------------------------------


class IngestLog(SQLModel, table=True):
    __tablename__ = "ingest_log"

    id: int | None = Field(default=None, primary_key=True)
    table_name: str
    filename: str
    rows_loaded: int
    rows_rejected: int
    rejects_json: str
    status: str
    created_at: datetime = Field(default_factory=utcnow)


class PlanRun(SQLModel, table=True):
    __tablename__ = "plan_runs"

    plan_id: str = Field(primary_key=True)
    run_id: str = Field(index=True)
    kind: str  # "base" or "scenario"
    weights_json: str
    scenario_json: str
    solver: str
    solver_status: str
    total_cost: float
    total_carbon_kg: float
    late_orders: int
    unmet_orders: int
    capacity_ok: bool
    eligibility_ok: bool
    delivery_ok: bool
    created_at: datetime = Field(default_factory=utcnow)


class PlanAllocation(SQLModel, table=True):
    __tablename__ = "plan_allocations"

    id: int | None = Field(default=None, primary_key=True)
    plan_id: str = Field(index=True)
    order_id: str
    plant: str | None = None
    week: int | None = None
    cost: float
    carbon_kg: float
    arrival: date | None = None
    on_time: bool
    days_late: int
    moved: bool = False
    base_plant: str | None = None


class AgentRun(SQLModel, table=True):
    __tablename__ = "agent_runs"

    run_id: str = Field(primary_key=True)
    request: str
    answer_type: str
    steps_json: str
    response_json: str
    llm_calls: int
    tokens: int
    latency_ms: int
    numbers_checked: int
    numbers_matched: int
    created_at: datetime = Field(default_factory=utcnow)
