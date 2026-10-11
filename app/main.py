"""FastAPI app: the four contract endpoints plus streaming, runs, data and auth."""

from __future__ import annotations

import asyncio
import json
import os
import threading
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlmodel import select

from app import auth
from app.agent.graph import run_request
from app.agent.llm import llm_status
from app.config import get_settings
from app.core.loader import ingest_csv
from app.dataset import validation_report
from app.db import get_engine, get_session, init_db, load_tables
from app.models import AgentRun

ROOT = Path(__file__).resolve().parents[1]
DATA_TABLES = ("orders", "plants", "transport_duties", "capacity_events")


class Weights(BaseModel):
    cost: float = 0.7
    carbon: float = 0.3
    lateness: float = 1.0


class AnalyzeRequest(BaseModel):
    request: str = Field(min_length=1, max_length=2000)
    weights: Weights | None = None
    scenario: dict | None = None


def _autoload() -> None:
    settings = get_settings()
    if not settings.autoload_sample or os.environ.get("AUTOLOAD_SAMPLE", "").lower() == "false":
        return
    if not load_tables()["orders"].empty:
        return
    sample = ROOT / "data" / "sample"
    if (sample / "orders.csv").is_file():
        for table in ("plants", "transport_duties", "orders", "capacity_events"):
            path = sample / f"{table}.csv"
            if path.is_file():
                ingest_csv(table, path.read_bytes(), str(path.resolve()))


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    _autoload()
    auth.ensure_demo_user()
    yield


app = FastAPI(title="Order Allocation API", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
app.include_router(auth.router)


@app.middleware("http")
async def security_headers(request, call_next):
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    return response


@app.get("/health")
def health():
    settings = get_settings()
    try:
        with get_engine().connect() as conn:
            conn.execute(text("select 1"))
        tables = load_tables()
        rows = {name: len(frame) for name, frame in tables.items()}
        store = "ok"
    except Exception:
        rows, store = {}, "error"
    return {
        "status": "ok" if store == "ok" else "degraded",
        "api": "ok",
        "data_store": store,
        "llm": llm_status(),
        "provider": settings.llm_provider,
        "model": settings.llm_model,
        "rows": rows,
    }


@app.post("/analyze")
def analyze(body: AnalyzeRequest):
    weights = body.weights.model_dump() if body.weights else None
    return run_request(body.request, weights, body.scenario)


@app.post("/analyze/stream")
async def analyze_stream(body: AnalyzeRequest):
    weights = body.weights.model_dump() if body.weights else None
    loop = asyncio.get_running_loop()
    queue: asyncio.Queue = asyncio.Queue()

    def emit(event: str, data) -> None:
        loop.call_soon_threadsafe(queue.put_nowait, (event, data))

    def worker() -> None:
        try:
            result = run_request(body.request, weights, body.scenario, on_event=emit)
            emit("result", result)
        except Exception as exc:  # noqa: BLE001
            emit("error", {"message": type(exc).__name__})
        emit("__end__", None)

    threading.Thread(target=worker, daemon=True).start()

    async def events():
        while True:
            try:
                event, data = await asyncio.wait_for(queue.get(), timeout=15)
            except TimeoutError:
                yield ": ping\n\n"
                continue
            if event == "__end__":
                break
            yield f"event: {event}\ndata: {json.dumps(data, default=str)}\n\n"

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.post("/ingest")
async def ingest(
    file: UploadFile = File(...),
    table: str | None = Form(None),
    meta: str | None = Form(None),
    mode: str = Form("replace"),
    table_q: str | None = Query(None, alias="table"),
):
    if meta:
        try:
            parsed = json.loads(meta)
            table, mode = parsed.get("table", table), parsed.get("mode", mode)
        except json.JSONDecodeError:
            raise HTTPException(422, 'meta must be JSON like {"table": "orders"}') from None
    table = table or table_q
    if not table:
        raise HTTPException(422, "say which table: form field 'table', 'meta' JSON, or ?table=")
    content = await file.read()
    if len(content) > get_settings().max_upload_mb * 1024 * 1024:
        raise HTTPException(413, "file too large")
    name = Path(file.filename or "upload.csv").name
    result = ingest_csv(table, content, name, mode)
    result["validation"] = validation_report()
    return result


@app.get("/validate")
def validate():
    return validation_report()


@app.get("/trace/{run_id}")
def trace(run_id: str):
    with get_session() as s:
        run = s.get(AgentRun, run_id)
    if not run:
        raise HTTPException(404, "run not found")
    response = json.loads(run.response_json)
    tables = load_tables()
    return {
        "run_id": run.run_id,
        "request": run.request,
        "answer_type": run.answer_type,
        "steps": json.loads(run.steps_json),
        "llm_calls": run.llm_calls,
        "tokens": run.tokens,
        "latency_ms": run.latency_ms,
        "number_check": {"checked": run.numbers_checked, "matched": run.numbers_matched},
        "data_used": {
            "rows": {k: len(v) for k, v in tables.items()},
            "planning_start": response.get("meta", {}).get("planning_start"),
            "capacity_events_active": response.get("meta", {}).get("events", []),
        },
        "created_at": run.created_at.isoformat(),
    }


@app.get("/runs")
def runs(limit: int = Query(20, ge=1, le=200)):
    with get_session() as s:
        rows = s.exec(select(AgentRun).order_by(AgentRun.created_at.desc()).limit(limit)).all()
    return [
        {
            "run_id": r.run_id,
            "request": r.request,
            "answer_type": r.answer_type,
            "created_at": r.created_at.isoformat(),
            "latency_ms": r.latency_ms,
        }
        for r in rows
    ]


@app.get("/runs/{run_id}")
def run_detail(run_id: str):
    with get_session() as s:
        run = s.get(AgentRun, run_id)
    if not run:
        raise HTTPException(404, "run not found")
    return json.loads(run.response_json)


@app.get("/data/{table}")
def data(
    table: str, q: str = "", limit: int = Query(100, ge=1, le=500), offset: int = Query(0, ge=0)
):
    if table not in DATA_TABLES:
        raise HTTPException(404, "unknown table")
    frame = load_tables()[table]
    if q:
        mask = (
            frame.astype(str)
            .apply(lambda col: col.str.contains(q, case=False, regex=False))
            .any(axis=1)
        )
        frame = frame[mask]
    page = frame.iloc[offset : offset + limit]
    return {
        "columns": list(frame.columns),
        "rows": json.loads(page.to_json(orient="records", date_format="iso")),
        "total": len(frame),
    }
