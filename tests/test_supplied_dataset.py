"""Offline integration checks for the bundled synthetic starter dataset."""

import json
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from backend.config import Settings, default_data_dir
from backend.data_store import DataStore, parse_history_csv

DATA_DIR = Path(__file__).resolve().parents[1] / "data"
DATA_FILES = ("employees.json", "events.json", "skills.json", "activity_history.csv")


@pytest.fixture(scope="module")
def source_payload():
    assert all((DATA_DIR / filename).is_file() for filename in DATA_FILES), (
        "The four bundled dataset files must be present in data/."
    )
    return {
        "employees": json.loads((DATA_DIR / "employees.json").read_text(encoding="utf-8-sig"))[
            "employees"
        ],
        "history": parse_history_csv(DATA_DIR / "activity_history.csv"),
    }


@pytest.fixture
def supplied_client(source_payload, monkeypatch):
    settings = Settings(data_dir=DATA_DIR, llm_api_key="")
    # main constructs a default app on import; keep it independent of local secrets.
    monkeypatch.setattr(Settings, "from_env", classmethod(lambda cls: settings))

    async def forbid_provider_request(*args, **kwargs):
        pytest.fail("Full-dataset integration tests must remain offline.")

    monkeypatch.setattr(httpx.AsyncClient, "request", forbid_provider_request)
    from backend.main import create_app

    app = create_app(settings=settings, data_store=DataStore(DATA_DIR))
    with TestClient(app) as client:
        assert app.state.llm_client is None
        yield client


def test_supplied_dataset_is_default_and_reports_counts_and_provenance(supplied_client):
    assert default_data_dir() == DATA_DIR
    store = supplied_client.app.state.data_store
    assert len(store.skills) == 60
    assert len(store.role_profiles) == 32
    response = supplied_client.get("/health")
    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "snapshot_date": "2026-10-01",
        "synthetic_data": True,
        "employees": 200,
        "events": 40,
        "history_records": 2743,
        "rationale_mode": "template",
    }


def test_post_review_learning_is_applied_once_across_source_reimports(
    supplied_client, source_payload
):
    assessed = next(row for row in source_payload["employees"] if row["employee_id"] == "E0001")
    assert assessed["skills"]["SK_APP_SECURITY"] == 0
    profile = supplied_client.get("/employees/E0001").json()
    record = next(row for row in profile["activity_history"] if row["record_id"] == "R002727")
    assert (record["event_id"], record["status"], record["date"]) == (
        "EV_011", "completed", "2026-09-25"
    )
    assert profile["last_review_date"] == "2026-09-11"
    assert profile["skills"]["SK_APP_SECURITY"] == 1
    store = supplied_client.app.state.data_store
    before = {key: employee.model_dump() for key, employee in store.employees.items()}
    for _ in range(2):
        response = supplied_client.post("/data/import", json=source_payload)
        assert response.status_code == 200
        assert response.json()["employees_imported"] == 200
        assert response.json()["history_imported"] == 2743
        assert {key: employee.model_dump() for key, employee in store.employees.items()} == before
        assert supplied_client.get("/health").json()["history_records"] == 2743


def test_all_employee_and_hr_reads_work_with_the_full_dataset(supplied_client):
    store = supplied_client.app.state.data_store
    without_recommendations = set()
    for employee_id in store.employees:
        profile = supplied_client.get(f"/employees/{employee_id}")
        assert profile.status_code == 200, employee_id
        assert profile.json()["employee_id"] == employee_id
        response = supplied_client.get(f"/employees/{employee_id}/recommendations")
        assert response.status_code == 200, employee_id
        recommendations = response.json()["recommendations"]
        assert len(recommendations) <= 3
        assert all(row["event_id"] in store.events and row["rationale"] for row in recommendations)
        if not recommendations:
            without_recommendations.add(employee_id)

    catalog = supplied_client.get("/skills")
    assert catalog.status_code == 200
    assert {row["skill_id"] for row in catalog.json()} == set(store.skills)
    gaps = supplied_client.get("/hr/skill-gaps")
    assert gaps.status_code == 200
    assert 0 < len(gaps.json()) <= 15
    assert all(row["total_gap"] > 0 and row["skill_id"] in store.skills for row in gaps.json())
    without = supplied_client.get("/hr/employees-without-recommendation")
    assert without.status_code == 200
    assert {row["employee_id"] for row in without.json()} == without_recommendations
    participation = supplied_client.get("/hr/participation-stats")
    assert participation.status_code == 200
    assert sum(row["total"] for row in participation.json()) == 2743


def test_completion_refresh_and_duplicate_conflict_survive_original_source_reimport(
    supplied_client, source_payload
):
    endpoint = "/employees/E0001"
    before = supplied_client.get(f"{endpoint}/recommendations").json()["recommendations"]
    assert "EV_005" in {row["event_id"] for row in before}
    response = supplied_client.post(f"{endpoint}/activities/EV_005/complete")
    assert response.status_code == 200
    completed = response.json()
    assert completed["skills"]["SK_API_DESIGN"] == 3
    assert completed["skills"]["SK_SYSTEM_DESIGN"] == 2
    assert "EV_005" not in {row["event_id"] for row in completed["recommendations"]}
    refreshed = supplied_client.get(f"{endpoint}/recommendations").json()["recommendations"]
    assert refreshed == completed["recommendations"]
    assert refreshed != before
    profile = supplied_client.get(endpoint).json()
    assert profile["skills"] == completed["skills"]
    assert supplied_client.get("/health").json()["history_records"] == 2744
    assert supplied_client.post(f"{endpoint}/activities/EV_005/complete").status_code == 409
    assert supplied_client.get(endpoint).json() == profile

    # These are the original assessments, never the already-derived API skills.
    assert supplied_client.post("/data/import", json=source_payload).status_code == 200
    assert supplied_client.get(endpoint).json() == profile
    assert supplied_client.get("/health").json()["history_records"] == 2744
    assert supplied_client.get(f"{endpoint}/recommendations").json()["recommendations"] == refreshed
