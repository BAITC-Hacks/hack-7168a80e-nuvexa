"""Offline API contract checks using a fresh synthetic dataset for every test."""

import json
from collections import Counter
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from backend.config import Settings
from backend.data_store import DataStore

SAMPLE_DATA = Path(__file__).resolve().parents[1] / "sample_data"


@pytest.fixture
def client(monkeypatch):
    """Exercise startup/shutdown without loading secrets or calling a provider."""
    settings = Settings(data_dir=SAMPLE_DATA, llm_api_key="")
    # main also exposes a module-level ASGI app; its initial construction must not
    # consult the developer's .env before this test creates its isolated app.
    monkeypatch.setattr(Settings, "from_env", classmethod(lambda cls: settings))

    async def forbid_provider_request(*args, **kwargs):
        pytest.fail("Offline API tests must not make provider requests.")

    monkeypatch.setattr(httpx.AsyncClient, "request", forbid_provider_request)
    from backend.main import create_app

    app = create_app(settings=settings, data_store=DataStore(SAMPLE_DATA))
    with TestClient(app) as test_client:
        assert app.state.llm_client is None
        yield test_client


def new_employee(client, employee_id="EMP_IMPORT"):
    employee = client.app.state.data_store.get_employee("EMP_002").model_dump(mode="json")
    employee.update(employee_id=employee_id, full_name="Imported Demo")
    return employee


def new_history(**overrides):
    return {
        "record_id": "REC_1000", "employee_id": "EMP_IMPORT", "event_id": "EV_002",
        "date": "2026-10-01", "due_date": None, "status": "completed",
        "completion_pct": 100, "score": None, "feedback_rating": None,
        "assigned_by": "self",
    } | overrides


def test_health_and_employee_contract_include_synthetic_provenance(client):
    health = client.get("/health")
    assert health.status_code == 200
    assert health.json() == {
        "status": "ok", "snapshot_date": "2026-10-01", "synthetic_data": True,
        "employees": 6, "events": 12, "history_records": 14, "rationale_mode": "template",
    }
    response = client.get("/employees/EMP_001")
    assert response.status_code == 200
    employee = response.json()
    assert employee["role"] == "Data Analyst"
    assert employee["grade"] == "Middle"
    assert employee["next_grade"] == "Senior"
    assert employee["manager_id"] == "EMP_004"
    gaps = {row["skill_id"]: row for row in employee["skill_gaps"]}
    # The Sep 17 club completion follows the Sep 15 assessment (level 1 -> 2).
    assert employee["skills"]["SK_COMMUNICATION"] == 2
    assert gaps["SK_COMMUNICATION"]["gap"] == 2
    assert gaps["SK_SQL"]["gap"] == 1
    assert gaps["SK_SQL"]["critical"] is True
    assert len(employee["activity_history"]) == 5
    assert all(row["event_title"] for row in employee["activity_history"])
    dates = [row["date"] for row in employee["activity_history"]]
    assert dates == sorted(dates, reverse=True)
    assert client.get("/employees/EMP_004").json()["manager_id"] is None
    catalog = client.get("/skills")
    assert catalog.status_code == 200
    assert {row["skill_id"] for row in catalog.json()} == {
        "SK_SQL", "SK_PYTHON", "SK_ANALYTICS", "SK_COMMUNICATION", "SK_LEADERSHIP",
    }


def test_recommend_complete_refresh_and_duplicate_conflict(client):
    response = client.get("/employees/EMP_001/recommendations")
    assert response.status_code == 200
    before = response.json()["recommendations"]
    assert [row["event_id"] for row in before[:2]] == ["EV_001", "EV_002"]
    assert before[0]["score"] == 3
    assert before[0]["closes_skills"] == ["SK_SQL"]
    assert before[0]["critical"] is True
    for row in before:
        assert set(row) == {
            "event_id", "title", "rationale", "score", "closes_skills", "critical",
            "duration_hours", "format",
        }
        assert len(row["rationale"]) >= 40
    assert {row["event_id"] for row in before}.isdisjoint({"EV_004", "EV_005", "EV_006", "EV_007", "EV_008"})

    response = client.post("/employees/EMP_001/activities/EV_001/complete")
    assert response.status_code == 200
    completed = response.json()
    assert completed["employee_id"] == "EMP_001"
    assert completed["event_id"] == "EV_001"
    assert completed["skills"]["SK_SQL"] == 4
    assert "EV_001" not in {row["event_id"] for row in completed["recommendations"]}
    assert completed["recommendations"] != before
    refreshed = client.get("/employees/EMP_001/recommendations").json()
    assert refreshed["recommendations"] == completed["recommendations"]
    profile = client.get("/employees/EMP_001").json()
    assert profile["skills"] == completed["skills"]
    records = [row for row in profile["activity_history"] if row["event_id"] == "EV_001"]
    assert len(records) == 1
    assert records[0]["status"] == "completed"
    assert records[0]["completion_pct"] == 100
    assert records[0]["date"] == "2026-10-01"
    assert records[0]["assigned_by"] == "self"

    repeated = client.post("/employees/EMP_001/activities/EV_001/complete")
    assert repeated.status_code == 409
    assert "already completed" in repeated.json()["message"].lower()
    assert client.get("/employees/EMP_001").json() == profile


def test_recurring_completion_can_repeat_and_respects_skill_ceiling(client):
    # EMP_001 already has a completed EV_036 record in the source data.
    for expected in (3, 4, 5, 5, 5):
        response = client.post("/employees/EMP_001/activities/EV_036/complete")
        assert response.status_code == 200
        assert response.json()["skills"]["SK_COMMUNICATION"] == expected
    profile = client.get("/employees/EMP_001").json()
    records = [row for row in profile["activity_history"] if row["event_id"] == "EV_036"]
    assert len(records) == 6
    assert len({row["record_id"] for row in records}) == 6


def test_lower_teaching_cap_never_reduces_existing_skill(client):
    response = client.post("/employees/EMP_001/activities/EV_006/complete")
    assert response.status_code == 200
    assert response.json()["skills"]["SK_SQL"] == 3
    assert client.get("/employees/EMP_001").json()["skills"]["SK_SQL"] == 3


def test_lead_has_no_next_grade_or_recommendations(client):
    response = client.get("/employees/EMP_004/recommendations")
    assert response.status_code == 200
    assert response.json() == {"employee_id": "EMP_004", "recommendations": []}
    profile = client.get("/employees/EMP_004").json()
    assert profile["next_grade"] is None
    assert profile["skill_gaps"] == []


@pytest.mark.parametrize("method,path", [
    ("get", "/employees/EMP_UNKNOWN"),
    ("get", "/employees/EMP_UNKNOWN/recommendations"),
    ("post", "/employees/EMP_UNKNOWN/activities/EV_001/complete"),
    ("post", "/employees/EMP_001/activities/EV_UNKNOWN/complete"),
])
def test_unknown_ids_are_readable_404s_without_mutation(client, method, path):
    before = client.get("/health").json()
    response = getattr(client, method)(path)
    assert response.status_code == 404
    assert "Unknown" in response.json()["message"]
    assert client.get("/health").json() == before


def test_hr_aggregates_use_reconciled_gaps_and_all_six_statuses(client):
    gaps = client.get("/hr/skill-gaps")
    assert gaps.status_code == 200
    actual = {row["skill_id"]: (row["total_gap"], row["employees_affected"]) for row in gaps.json()}
    assert actual == {
        "SK_COMMUNICATION": (6, 4), "SK_PYTHON": (5, 4), "SK_SQL": (5, 4),
        "SK_LEADERSHIP": (4, 4), "SK_ANALYTICS": (3, 3),
    }
    assert [row["total_gap"] for row in gaps.json()] == [6, 5, 5, 4, 3]
    assert all(row["skill_name"] for row in gaps.json())
    without = client.get("/hr/employees-without-recommendation")
    assert without.status_code == 200
    assert without.json() == [{
        "employee_id": "EMP_004", "full_name": "Robin Demo",
        "role": "Data Analyst", "grade": "Lead",
    }]

    response = client.get("/hr/participation-stats")
    assert response.status_code == 200
    rows = response.json()
    counts = Counter()
    statuses = ("completed", "declined", "no_show", "dropped", "in_progress", "overdue")
    for row in rows:
        assert row["title"]
        assert row["total"] == sum(row[status] for status in statuses)
        counts.update({status: row[status] for status in statuses})
    assert counts == {"completed": 6, "declined": 2, "no_show": 2, "dropped": 1, "in_progress": 2, "overdue": 1}
    assert sum(row["total"] for row in rows) == 14
    assert [row["total"] for row in rows] == sorted((row["total"] for row in rows), reverse=True)
    onboarding = next(row for row in rows if row["event_id"] == "EV_004")
    assert (onboarding["completed"], onboarding["overdue"], onboarding["total"]) == (2, 1, 3)


def test_combined_import_rejects_unknown_event_without_partial_employee_write(client):
    before = client.get("/health").json()
    response = client.post("/data/import", json={
        "employees": [new_employee(client)],
        "history": [new_history(event_id="EV_UNKNOWN")],
    })
    assert response.status_code == 422
    assert "Unknown event_id" in response.json()["message"]
    assert client.get("/employees/EMP_IMPORT").status_code == 404
    assert client.get("/health").json() == before


def test_combined_import_supports_new_references_and_idempotent_upsert(client):
    payload = {"employees": [new_employee(client)], "history": [new_history()]}
    for _ in range(2):
        response = client.post("/data/import", json=payload)
        assert response.status_code == 200
        assert response.json()["employees_imported"] == 1
        assert response.json()["history_imported"] == 1
    health = client.get("/health").json()
    assert (health["employees"], health["history_records"]) == (7, 15)
    imported = client.get("/employees/EMP_IMPORT").json()
    # Post-review completion applies exactly once across repeated imports.
    assert imported["skills"]["SK_PYTHON"] == 2
    assert len(imported["activity_history"]) == 1
    assert imported["activity_history"][0]["record_id"] == "REC_1000"

    payload["employees"][0]["full_name"] = "Updated Demo"
    payload["history"][0]["feedback_rating"] = 2
    assert client.post("/data/import", json=payload).status_code == 200
    updated = client.get("/employees/EMP_IMPORT").json()
    assert updated["full_name"] == "Updated Demo"
    assert updated["activity_history"][0]["feedback_rating"] == 2
    assert client.get("/health").json()["history_records"] == 15


def test_history_csv_wrapper_preserves_nulls_and_strings(client):
    csv = (
        "record_id,employee_id,event_id,date,due_date,status,completion_pct,score,feedback_rating,assigned_by\n"
        "REC_2000,EMP_002,EV_002,2026-10-01,,in_progress,25,,,self\n"
    )
    response = client.post("/data/import", json={"type": "history", "data": csv})
    assert response.status_code == 200
    assert response.json()["history_imported"] == 1
    record = next(row for row in client.get("/employees/EMP_002").json()["activity_history"] if row["record_id"] == "REC_2000")
    assert record["completion_pct"] == 25
    assert record["due_date"] is record["score"] is record["feedback_rating"] is None


def test_employee_json_wrapper_accepts_dataset_shape(client):
    payload = {"meta": {"synthetic": True}, "employees": [new_employee(client)]}
    response = client.post("/data/import", json={"type": "employees", "data": json.dumps(payload)})
    assert response.status_code == 200
    assert response.json()["employees_imported"] == 1
    assert client.get("/employees/EMP_IMPORT").status_code == 200


@pytest.mark.parametrize("payload", [
    {},
    {"employees": [{"employee_id": "EMP_INVALID"}]},
    {"history": [new_history(employee_id="EMP_UNKNOWN")]},
    {"history": [new_history(employee_id="EMP_001", status="unknown")]},
    {"history": [new_history(employee_id="EMP_001", completion_pct=101)]},
    {"history": [new_history(employee_id="EMP_001", feedback_rating=6)]},
    {"employees": [], "unexpected": True},
    {"type": "history", "data": "wrong,header\none,two\n"},
    {"type": "employees", "data": "{not json"},
    {"type": "employees", "data": {"employee": []}},
])
def test_invalid_imports_return_422_and_leave_dataset_unchanged(client, payload):
    before = client.get("/health").json()
    response = client.post("/data/import", json=payload)
    assert response.status_code == 422
    assert response.json()["message"]
    assert client.get("/health").json() == before


@pytest.mark.parametrize("skill_value", [-1, 6, True, 2.5])
def test_invalid_employee_skill_levels_are_rejected(client, skill_value):
    employee = new_employee(client)
    employee["skills"]["SK_SQL"] = skill_value
    response = client.post("/data/import", json={"employees": [employee]})
    assert response.status_code == 422
    assert client.get("/employees/EMP_IMPORT").status_code == 404


@pytest.mark.parametrize("top_n", [0, 4, "invalid"])
def test_recommendation_limits_validate_query(client, top_n):
    response = client.get("/employees/EMP_001/recommendations", params={"top_n": top_n})
    assert response.status_code == 422
    assert response.json()["message"]


def test_recommendation_limit_is_respected(client):
    response = client.get("/employees/EMP_001/recommendations", params={"top_n": 1})
    assert response.status_code == 200
    assert len(response.json()["recommendations"]) == 1


def test_cors_permits_frontend_and_refuses_unconfigured_origin(client):
    headers = {
        "Origin": "http://localhost:5173", "Access-Control-Request-Method": "POST",
        "Access-Control-Request-Headers": "Content-Type",
    }
    allowed = client.options("/data/import", headers=headers)
    assert allowed.status_code == 200
    assert allowed.headers["access-control-allow-origin"] == headers["Origin"]
    denied = client.options("/data/import", headers=headers | {"Origin": "https://unconfigured.invalid"})
    assert denied.status_code == 400
    assert "access-control-allow-origin" not in denied.headers


def test_openapi_schema_exposes_frontend_routes(client):
    response = client.get("/openapi.json")
    assert response.status_code == 200
    schema = response.json()
    assert schema["info"]["title"] == "Career Quest API"
    expected = {
        "/health": "get", "/skills": "get", "/employees/{employee_id}": "get",
        "/employees/{employee_id}/recommendations": "get",
        "/employees/{employee_id}/activities/{event_id}/complete": "post",
        "/hr/skill-gaps": "get", "/hr/employees-without-recommendation": "get",
        "/hr/participation-stats": "get", "/data/import": "post",
    }
    for path, method in expected.items():
        assert method in schema["paths"][path]
    assert "Recommendation" in schema["components"]["schemas"]
    assert "ActivityRecord" in schema["components"]["schemas"]
