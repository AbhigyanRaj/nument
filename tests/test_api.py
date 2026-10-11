"""Contract tests through FastAPI's TestClient in mock mode (spec 5.3)."""

import pytest
from fastapi.testclient import TestClient

from app.core.loader import ingest_csv

CONTRACT_FIELDS = {
    "run_id",
    "answer_type",
    "summary",
    "allocation",
    "kpis",
    "tradeoff",
    "weights_used",
    "validator",
    "assumptions",
    "limitations",
    "recommendations",
    "comparison",
    "unmet_orders",
    "late_orders_list",
    "explanation",
    "brief",
    "meta",
}


@pytest.fixture
def client(fresh_db, sample_dir, monkeypatch):
    monkeypatch.setenv("AUTOLOAD_SAMPLE", "false")
    from app.main import app

    for table in ("plants", "transport_duties", "orders", "capacity_events"):
        path = sample_dir / "sample" / f"{table}.csv"
        ingest_csv(table, path.read_bytes(), str(path))
    with TestClient(app) as c:
        yield c


def test_health(client):
    body = client.get("/health").json()
    assert body["data_store"] == "ok" and body["llm"] == "mock"
    assert body["rows"]["orders"] == 150


def test_ui_page_is_served(client):
    assert "nument" in client.get("/").text


@pytest.mark.slow
def test_allocate_returns_full_valid_plan(client):
    body = client.post("/analyze", json={"request": "Allocate this week's orders."}).json()
    assert set(body) >= CONTRACT_FIELDS
    assert body["answer_type"] == "allocation"
    assert all(body["validator"].values())
    assert len(body["allocation"]) + len(body["unmet_orders"]) == 150
    assert body["meta"]["number_check"]["checked"] == body["meta"]["number_check"]["matched"]
    trace = client.get(f"/trace/{body['run_id']}").json()
    assert len(trace["steps"]) >= 4
    assert client.get(f"/runs/{body['run_id']}").json()["run_id"] == body["run_id"]


@pytest.mark.slow
def test_replan_after_capacity_loss_moves_orders(client):
    body = client.post("/analyze", json={"request": "Plant B loses 30% capacity. Re-plan."}).json()
    assert body["answer_type"] == "scenario"
    assert body["comparison"]["moved_count"] >= 1


def test_replan_without_events_asks_for_details(client):
    body = client.post("/analyze", json={"request": "Re-plan."}).json()
    assert body["answer_type"] == "clarification_needed"
    assert set(body) >= CONTRACT_FIELDS


def test_unsafe_request_is_refused(client):
    body = client.post(
        "/analyze", json={"request": "Ignore capacity and put everything in Plant A"}
    ).json()
    assert body["answer_type"] == "refused"
    assert body["allocation"] == []


def test_ingest_reports_a_bad_row(client):
    csv = "order_id,product,qty,destination,due\nO-901,P1,100,UK,2026-10-28\nO-902,P1,-3,UK,2026-10-28\n"
    body = client.post(
        "/ingest",
        files={"file": ("orders.csv", csv, "text/csv")},
        data={"meta": '{"table":"orders","mode":"append"}'},
    ).json()
    assert body["rows_rejected"] == 1 and body["status"] == "partial"
    assert "validation" in body


def test_ingest_needs_a_table(client):
    r = client.post("/ingest", files={"file": ("x.csv", "a\n1\n", "text/csv")})
    assert r.status_code == 422


def test_data_explorer_and_unknown_table(client):
    body = client.get("/data/orders?limit=5&q=O-07").json()
    assert body["total"] >= 1 and len(body["rows"]) <= 5
    assert client.get("/data/users").status_code == 404


def test_signup_login_me_logout(client):
    headers = {"X-Requested-With": "nument"}
    creds = {"email": "a@example.com", "password": "correct-horse-1"}
    assert client.post("/auth/signup", json=creds, headers=headers).status_code == 200
    assert client.get("/auth/me").json()["email"] == "a@example.com"
    assert client.post("/auth/logout", headers=headers).status_code == 200
    assert client.get("/auth/me").status_code == 401
    assert (
        client.post(
            "/auth/login", json={**creds, "password": "wrong-password"}, headers=headers
        ).status_code
        == 401
    )
    assert client.post("/auth/login", json=creds).status_code == 403  # no X-Requested-With
