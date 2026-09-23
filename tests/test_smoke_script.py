"""Offline regression coverage for the command-line integration smoke checks."""

import copy
from dataclasses import dataclass, field

import httpx
import pytest

from scripts.e2e_smoke_test import main, rationale_factors, run_smoke

EMPLOYEE_ID = "TEST_EMPLOYEE"
EMPLOYEE_PATH = f"/employees/{EMPLOYEE_ID}"
HR_PATHS = (
    "/hr/skill-gaps", "/hr/employees-without-recommendation", "/hr/participation-stats",
)


@dataclass
class FakeAPI:
    """A queue of observable HTTP responses, independent of smoke internals."""

    routes: dict[tuple[str, str], list]
    events: dict
    requests: list[tuple[str, str]] = field(default_factory=list)

    def request(self, request):
        key = (request.method, request.url.path)
        self.requests.append(key)
        assert key in self.routes, f"Unexpected request: {key}"
        queue = self.routes[key]
        response = queue.pop(0) if len(queue) > 1 else queue[0]
        if isinstance(response, Exception):
            raise response
        if isinstance(response, httpx.Response):
            return response
        return httpx.Response(200, json=response)

    def run(self, *, clock=lambda: 0.0):
        output = []
        with httpx.Client(
            base_url="http://smoke.test", transport=httpx.MockTransport(self.request)
        ) as client:
            code = run_smoke(client, EMPLOYEE_ID, self.events, emit=output.append, clock=clock)
        return code, "\n".join(output)


def make_api(event_id="EV_TEST", initial_level=1, cap=3):
    recommendation = {
        "event_id": event_id, "title": "Develop Python",
        "rationale": "Your level is 1 versus 3 required; this critical course reduces the skill gap.",
        "score": 2.0, "closes_skills": ["SK_PYTHON"], "critical": True,
        "duration_hours": 2, "format": "online",
    }
    recommendations = {"employee_id": EMPLOYEE_ID, "recommendations": [recommendation]}
    empty = {"employee_id": EMPLOYEE_ID, "recommendations": []}
    before = {
        "employee_id": EMPLOYEE_ID, "role": "Engineer", "grade": "Junior",
        "skills": {"SK_PYTHON": initial_level, "SK_OTHER": 4}, "activity_history": [],
    }
    after = copy.deepcopy(before)
    after["skills"]["SK_PYTHON"] = max(initial_level, min(cap, initial_level + 1))
    after["activity_history"] = [{"event_id": event_id, "status": "completed"}]
    completion = empty | {"event_id": event_id, "skills": copy.deepcopy(after["skills"])}
    participation = {
        "event_id": event_id, "title": "Develop Python", "completed": 1,
        "declined": 0, "no_show": 0, "dropped": 0, "in_progress": 0,
        "overdue": 0, "total": 1,
    }
    return FakeAPI(
        routes={
            ("GET", EMPLOYEE_PATH): [before, after],
            ("GET", f"{EMPLOYEE_PATH}/recommendations"): [recommendations, empty],
            ("POST", f"{EMPLOYEE_PATH}/activities/{event_id}/complete"): [completion],
            ("GET", HR_PATHS[0]): [[{
                "skill_id": "SK_PYTHON", "skill_name": "Python",
                "total_gap": 1, "employees_affected": 1,
            }]],
            ("GET", HR_PATHS[1]): [[]],
            ("GET", HR_PATHS[2]): [[participation]],
        },
        events={event_id: {
            "event_id": event_id,
            "develops_skills": [{"skill_id": "SK_PYTHON", "gain": 1, "max_level": cap}],
        }},
    )


def test_success_exercises_completion_persistence_refresh_and_all_hr_routes():
    api = make_api()
    code, output = api.run()
    assert code == 0
    assert "PASS summary: 7 passed, 0 failed, 0 skipped" in output
    assert "SK_PYTHON: 1 -> 2" in output
    assert "Completed EV_TEST disappeared: yes" in output
    assert api.requests.count(("GET", EMPLOYEE_PATH)) == 2
    assert sum(method == "POST" for method, _ in api.requests) == 1
    assert all(("GET", path) in api.requests for path in HR_PATHS)


@pytest.mark.parametrize("elapsed", [10.0, 10.01])
def test_ten_second_or_slower_recommendations_fail_but_hr_checks_continue(elapsed):
    api = make_api()
    times = iter([0, elapsed, elapsed, elapsed + 0.1])
    code, output = api.run(clock=lambda: next(times))
    assert code == 1
    assert "FAIL 2 recommendations and latency" in output
    assert "10s budget" in output
    assert "SKIP 3 complete first activity" in output
    assert not any(method == "POST" for method, _ in api.requests)
    assert all(("GET", path) in api.requests for path in HR_PATHS)
    assert "FAIL summary" in output


@pytest.mark.parametrize("response", [
    httpx.Response(404, json={"detail": "Unknown employee"}),
    httpx.Response(200, text="not JSON"),
    httpx.ConnectError("backend unavailable"),
    {"employee_id": EMPLOYEE_ID, "role": "Engineer", "grade": "Junior",
     "skills": {"SK_PYTHON": True}},
])
def test_profile_errors_are_reported_without_completing_an_activity(response):
    api = make_api()
    api.routes[("GET", EMPLOYEE_PATH)] = [response]
    code, output = api.run()
    assert code == 1
    assert "FAIL 1 employee profile" in output
    assert "SKIP 3 complete first activity" in output
    assert not any(method == "POST" for method, _ in api.requests)
    assert all(("GET", path) in api.requests for path in HR_PATHS)


@pytest.mark.parametrize("problem", ["wrong_employee", "short_rationale", "duplicate_event"])
def test_malformed_recommendations_fail_before_mutation(problem):
    api = make_api()
    payload = api.routes[("GET", f"{EMPLOYEE_PATH}/recommendations")][0]
    if problem == "wrong_employee":
        payload["employee_id"] = "SOMEONE_ELSE"
    elif problem == "short_rationale":
        payload["recommendations"][0]["rationale"] = "Good course"
    else:
        payload["recommendations"].append(copy.deepcopy(payload["recommendations"][0]))
    code, output = api.run()
    assert code == 1
    assert "FAIL 2 recommendations and latency" in output
    assert not any(method == "POST" for method, _ in api.requests)


def test_empty_recommendations_skip_only_completion():
    api = make_api()
    api.routes[("GET", f"{EMPLOYEE_PATH}/recommendations")] = [
        {"employee_id": EMPLOYEE_ID, "recommendations": []},
    ]
    code, output = api.run()
    assert code == 0
    assert "SKIP 3 complete first activity: no recommendations" in output
    assert "PASS summary: 6 passed, 0 failed, 1 skipped" in output
    assert not any(method == "POST" for method, _ in api.requests)


@pytest.mark.parametrize(("event_id", "expected_code"), [("EV_TEST", 1), ("EV_036", 0)])
def test_only_recurring_club_may_remain_recommended_after_completion(event_id, expected_code):
    api = make_api(event_id)
    queue = api.routes[("GET", f"{EMPLOYEE_PATH}/recommendations")]
    queue[1] = copy.deepcopy(queue[0])
    code, output = api.run()
    assert code == expected_code
    assert f"Completed {event_id} disappeared: no" in output
    if expected_code:
        assert "FAIL 4 refreshed recommendations" in output
    else:
        assert "EV_036 is repeatable" in output


@pytest.mark.parametrize("level", [3, 4])
def test_already_capped_or_above_cap_skill_stays_unchanged(level):
    api = make_api(initial_level=level, cap=3)
    code, output = api.run()
    assert code == 0
    assert f"SK_PYTHON: {level} -> {level}" in output


@pytest.mark.parametrize("problem", [
    "no_gain", "wrong_gain", "lost_other_skill", "unpersisted", "missing_history",
])
def test_completion_must_change_expected_skills_and_persist_the_record(problem):
    api = make_api()
    completion = api.routes[("POST", f"{EMPLOYEE_PATH}/activities/EV_TEST/complete")][0]
    after = api.routes[("GET", EMPLOYEE_PATH)][1]
    if problem == "no_gain":
        completion["skills"]["SK_PYTHON"] = 1
    elif problem == "wrong_gain":
        completion["skills"]["SK_PYTHON"] = 3
    elif problem == "lost_other_skill":
        del completion["skills"]["SK_OTHER"]
    elif problem == "unpersisted":
        after["skills"]["SK_PYTHON"] = 1
    else:
        after["activity_history"] = []
    code, output = api.run()
    assert code == 1
    assert "FAIL 3 complete first activity and verify skill gains" in output
    assert all(("GET", path) in api.requests for path in HR_PATHS)


@pytest.mark.parametrize("malformed_history", [["not an object"], {"event_id": "EV_TEST"}])
def test_malformed_refreshed_history_produces_failure_summary_not_a_crash(malformed_history):
    api = make_api()
    api.routes[("GET", EMPLOYEE_PATH)][1]["activity_history"] = malformed_history
    code, output = api.run()
    assert code == 1
    assert "FAIL 3 complete first activity and verify skill gains" in output
    assert "FAIL summary" in output
    assert all(("GET", path) in api.requests for path in HR_PATHS)


def test_wrong_hr_totals_fail_after_successful_employee_flow():
    api = make_api()
    api.routes[("GET", HR_PATHS[2])][0][0]["total"] = 2
    code, output = api.run()
    assert code == 1
    assert "FAIL 5 /hr/participation-stats: participation total mismatch" in output


@pytest.mark.parametrize("text", [
    "Your level is 1, required 3. It is critical; you previously declined. It reduces the gap.",
    "Ваш уровень 1, требуется 3. Навык критичен; в истории есть отказ. Разрыв сокращается.",
    "Сіздің деңгейіңіз 1, талап 3. Дағды маңызды; тарихта бас тарту бар. Алшақтық қысқарады.",
])
def test_heuristic_detects_four_distinct_factors_in_supported_languages(text):
    assert set(rationale_factors(text)) == {
        "level/requirement", "criticality", "history", "gap reduction",
    }


def test_low_factor_count_is_a_warning_without_failing_otherwise_valid_flow():
    api = make_api()
    api.routes[("GET", f"{EMPLOYEE_PATH}/recommendations")][0]["recommendations"][0][
        "rationale"
    ] = "This course provides a useful introduction to the subject and practical exercises."
    code, output = api.run()
    assert code == 0
    assert "WARNING EV_TEST: fewer than two rationale factors detected" in output


def test_missing_local_catalog_fails_before_any_network_request(tmp_path, capsys):
    assert main([EMPLOYEE_ID, "--data-dir", str(tmp_path)]) == 1
    assert "FAIL setup" in capsys.readouterr().err


def test_invalid_base_url_port_reports_setup_failure_without_a_traceback(capsys):
    assert main([EMPLOYEE_ID, "--base-url", "http://localhost:abc"]) == 1
    assert "FAIL setup" in capsys.readouterr().err
