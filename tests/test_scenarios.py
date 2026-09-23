"""Scenario discovery must report real cases without relaxing the predicates."""

import copy
import json
import subprocess
import sys

import pytest

from scripts.find_test_scenarios import DEFAULT_DATA_DIR, find_scenarios, scan_scenarios


@pytest.fixture
def scenario_input():
    return {
        "employees": [{
            "employee_id": "TEST_EMPLOYEE", "role": "Engineer", "grade": "Junior",
            "tenure_months": 12,
            "skills": {"SOFT": 1, "HARD": 2, "OTHER": 3},
            "last_review_date": "2026-01-01",
            "career_goal": {"target_role": "Manager", "target_grade": "Lead"},
        }],
        "skills_document": {
            "skills": [
                {"skill_id": "SOFT", "type": "soft"},
                {"skill_id": "HARD", "type": "hard"},
                {"skill_id": "OTHER", "type": "hard"},
            ],
            "role_profiles": [{
                "role": "Engineer", "grade": "Middle",
                "required_skills": {"SOFT": 4, "HARD": 3, "OTHER": 4},
                "critical_skills": ["HARD"],
            }],
        },
        "events": [
            {"event_id": "EV_SOFT", "develops_skills": [
                {"skill_id": "SOFT", "gain": 3, "max_level": 5},
            ]},
            {"event_id": "EV_HARD", "develops_skills": [
                {"skill_id": "HARD", "gain": 1, "max_level": 5},
            ]},
            {"event_id": "EV_004", "develops_skills": []},
        ],
        "history": [
            {"record_id": "R1", "employee_id": "TEST_EMPLOYEE", "event_id": "EV_SOFT",
             "status": "declined", "date": "2026-01-02"},
            {"record_id": "R2", "employee_id": "TEST_EMPLOYEE", "event_id": "EV_SOFT",
             "status": "no_show", "date": "2026-01-03"},
        ],
    }


def test_conflict_uses_current_roles_next_grade_and_exact_negative_history(scenario_input):
    # A completed event is evidence in the source, not another negative record
    # or a reason to replace raw assessment levels with the API's derived skills.
    scenario_input["history"].append(scenario_input["history"][0] | {
        "record_id": "R3", "status": "completed", "date": "2026-02-01",
    })
    case, = scan_scenarios(**scenario_input)["gap_vs_history_conflict"]
    assert case["next_grade"] == "Middle"
    assert case["soft_skill"] == {
        "skill_id": "SOFT", "current_level": 1, "required_level": 4, "gap": 3,
    }
    assert case["hard_critical_skill"]["gap"] == 1
    assert case["history_count"] == 2
    assert [row["record_id"] for row in case["history"]] == ["R1", "R2"]


@pytest.mark.parametrize("invalid_case", [
    "one_negative", "different_skill", "different_employee", "nonnegative_status",
    "hard_gap_zero", "hard_gap_equal", "hard_not_critical", "soft_not_largest",
])
def test_conflict_rejects_near_matches(scenario_input, invalid_case):
    if invalid_case == "one_negative":
        scenario_input["history"].pop()
    elif invalid_case == "different_skill":
        scenario_input["history"][1]["event_id"] = "EV_HARD"
    elif invalid_case == "different_employee":
        scenario_input["history"][1]["employee_id"] = "SOMEONE_ELSE"
    elif invalid_case == "nonnegative_status":
        scenario_input["history"][1]["status"] = "in_progress"
    elif invalid_case == "hard_gap_zero":
        scenario_input["employees"][0]["skills"]["HARD"] = 3
    elif invalid_case == "hard_gap_equal":
        scenario_input["employees"][0]["skills"]["HARD"] = 0
    elif invalid_case == "hard_not_critical":
        scenario_input["skills_document"]["role_profiles"][0]["critical_skills"] = []
    elif invalid_case == "soft_not_largest":
        scenario_input["employees"][0]["skills"]["OTHER"] = 0
    assert scan_scenarios(**scenario_input)["gap_vs_history_conflict"] == []


def test_largest_gap_tie_qualifies_and_missing_skill_is_zero(scenario_input):
    employee = scenario_input["employees"][0]
    del employee["skills"]["SOFT"]
    employee["skills"]["OTHER"] = 0
    case, = scan_scenarios(**scenario_input)["gap_vs_history_conflict"]
    assert case["soft_skill"]["gap"] == 4
    assert case["soft_skill"]["current_level"] == 0


@pytest.mark.parametrize(("tenure", "events", "expected"), [
    (0, [], True), (3, ["EV_004"], True), (4, ["EV_004"], False),
    (1, ["EV_004", "EV_SOFT"], False),
])
def test_new_hire_requires_onboarding_only_and_allows_leads(
    scenario_input, tenure, events, expected,
):
    scenario_input["employees"][0].update(tenure_months=tenure, grade="Lead")
    scenario_input["history"] = [
        scenario_input["history"][0] | {"record_id": f"R{i}", "event_id": event}
        for i, event in enumerate(events)
    ]
    result = scan_scenarios(**scenario_input)
    assert bool(result["new_hire"]) is expected
    assert result["near_grade_ceiling"] == []
    assert result["gap_vs_history_conflict"] == []


@pytest.mark.parametrize(("skills", "expected_total"), [
    ({"SOFT": 4, "HARD": 2, "OTHER": 3}, 2),
    ({"SOFT": 5, "HARD": 3, "OTHER": 4}, 0),
    ({"SOFT": 5, "HARD": 1, "OTHER": 3}, None),
    ({"SOFT": 5, "OTHER": 5}, None),
])
def test_ceiling_sums_only_positive_gaps_and_counts_missing_skills(
    scenario_input, skills, expected_total,
):
    scenario_input["employees"][0]["skills"] = skills
    result = scan_scenarios(**scenario_input)["near_grade_ceiling"]
    if expected_total is None:
        assert result == []
    else:
        case, = result
        assert case["total_gap"] == expected_total
        assert all(gap["gap"] > 0 for gap in case["remaining_gaps"])


def test_results_are_sorted_limited_and_do_not_mutate_input(scenario_input):
    scenario_input["history"] = []
    scenario_input["employees"] = [
        scenario_input["employees"][0] | {"employee_id": f"E{i}", "tenure_months": 1}
        for i in reversed(range(5))
    ]
    before = copy.deepcopy(scenario_input)
    result = scan_scenarios(**scenario_input)
    assert [row["employee_id"] for row in result["new_hire"]] == ["E0", "E1", "E2"]
    assert scenario_input == before


def test_supplied_data_does_not_invent_absent_cases():
    results = find_scenarios()
    case, = results["gap_vs_history_conflict"]
    assert case["employee_id"] == "E0099"
    assert (case["soft_skill"]["gap"], case["hard_critical_skill"]["gap"]) == (3, 1)
    assert case["history_count"] == 2
    assert results["new_hire"] == []
    assert results["near_grade_ceiling"] == []


def test_cli_defaults_to_repository_data_from_other_working_directory(tmp_path):
    script = DEFAULT_DATA_DIR.parent / "scripts" / "find_test_scenarios.py"
    result = subprocess.run(
        [sys.executable, str(script), "--json"], cwd=tmp_path,
        capture_output=True, text=True, check=True,
    )
    assert json.loads(result.stdout)["scenarios"] == find_scenarios()


def test_missing_dataset_returns_a_clear_nonzero_exit(tmp_path):
    script = DEFAULT_DATA_DIR.parent / "scripts" / "find_test_scenarios.py"
    result = subprocess.run(
        [sys.executable, str(script), "--data-dir", str(tmp_path)],
        capture_output=True, text=True,
    )
    assert result.returncode == 1
    assert "FAIL: could not scan dataset" in result.stderr
    assert "Traceback" not in result.stderr
