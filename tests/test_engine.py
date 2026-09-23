"""Focused behavioral tests for validated schemas and deterministic scoring."""

from datetime import date

import pytest
from pydantic import ValidationError

from backend.config import SNAPSHOT_DATE
from backend.models import ActivityRecord, Employee, Event, RoleProfile
from backend.recommendation_engine import (
    CRITICAL_BONUS,
    compute_participation_factors,
    compute_participation_penalty,
    compute_skill_gaps,
    filter_eligible_events,
    recommend_next_steps,
    score_event,
)


def employee(**overrides) -> Employee:
    """Small complete profile used only by tests, not production seed data."""
    fields = {
        "employee_id": "EMP_TEST",
        "full_name": "Test Employee",
        "department": "Engineering",
        "role": "Engineer",
        "grade": "Junior",
        "hire_date": "2026-01-01",
        "tenure_months": 9,
        "work_format": "hybrid",
        "preferred_language": "en",
        "skills": {"technical": 1, "communication": 1},
    }
    return Employee.model_validate(fields | overrides)


def event(event_id="EV_TEST", **overrides) -> Event:
    fields = {
        "event_id": event_id,
        "title": "Practice",
        "description": "Practice an applicable skill.",
        "type": "workshop",
        "format": "self_paced",
        "duration_hours": 2,
        "mandatory": False,
        "target_roles": ["Engineer"],
        "target_grades": ["Junior", "Middle", "Senior"],
        "develops_skills": [{"skill_id": "technical", "gain": 1, "max_level": 5}],
        "prerequisites": {},
        "upcoming_sessions": [],
    }
    return Event.model_validate(fields | overrides)


def history(record_id="REC_TEST", **overrides) -> ActivityRecord:
    fields = {
        "record_id": record_id,
        "employee_id": "EMP_TEST",
        "event_id": "EV_TEST",
        "date": "2026-09-01",
        "status": "completed",
        "completion_pct": 100,
        "assigned_by": "self",
    }
    return ActivityRecord.model_validate(fields | overrides)


def profile(**overrides) -> RoleProfile:
    return RoleProfile.model_validate(
        {
            "role": "Engineer",
            "grade": "Middle",
            "required_skills": {"technical": 3, "communication": 4},
            "critical_skills": ["technical"],
        }
        | overrides
    )


class MemoryStore:
    """Structural DataStore substitute keeps orchestration tests free of filesystem I/O."""

    def __init__(self, person, events, role_profile=None, records=None):
        self.employees = {person.employee_id: person}
        self.events = {item.event_id: item for item in events}
        self.role_profiles = [role_profile or profile()]
        self.records = records or []

    def get_employee(self, employee_id):
        return self.employees.get(employee_id)

    def get_employee_history(self, employee_id):
        return [record for record in self.records if record.employee_id == employee_id]

    def get_next_grade(self, role, grade):
        return {"Junior": "Middle", "Middle": "Senior", "Senior": "Lead", "Lead": None}[grade]

    def get_role_profile(self, role, grade):
        return next((item for item in self.role_profiles if item.role == role and item.grade == grade), None)


def test_models_parse_dates_and_preserve_nullable_fields():
    person = employee()
    assert person.hire_date == date(2026, 1, 1)
    assert person.manager_id is None
    assert person.career_goal is None
    assert person.last_review_date is None
    record = history()
    assert record.date == date(2026, 9, 1)
    assert record.due_date is record.score is record.feedback_rating is None
    assert event(upcoming_sessions=["2026-10-01"]).upcoming_sessions == [SNAPSHOT_DATE]


@pytest.mark.parametrize(
    "changes",
    [
        {"grade": "Principal"},
        {"preferred_language": "fr"},
        {"full_name": "  "},
        {"tenure_months": -1},
        {"skills": {"technical": 6}},
        {"skills": {"technical": 1.5}},
        {"skills": {"technical": True}},
        {"skills": {"": 1}},
        {"unexpected": "ignored?"},
    ],
)
def test_employee_rejects_invalid_or_unknown_values(changes):
    with pytest.raises(ValidationError):
        employee(**changes)


@pytest.mark.parametrize(
    "changes",
    [{"status": "unknown"}, {"completion_pct": 101}, {"score": -1}, {"feedback_rating": 0}],
)
def test_history_rejects_out_of_range_values(changes):
    with pytest.raises(ValidationError):
        history(**changes)


def test_gaps_weight_critical_skills_and_include_absent_skills():
    person = employee(skills={"technical": 1, "satisfied": 5})
    target = profile(required_skills={"technical": 3, "communication": 3, "satisfied": 2})
    gaps = compute_skill_gaps(person, target)
    assert [(item.skill_id, item.gap, item.weighted_gap) for item in gaps] == [
        ("technical", 2, 4), ("communication", 3, 3)
    ]
    assert gaps[1].current_level == 0
    assert compute_skill_gaps(employee(grade="Lead"), target) == []


@pytest.mark.parametrize(
    "changes",
    [
        {"target_roles": ["Analyst"]},
        {"target_grades": ["Senior"]},
        {"mandatory": True},
        {"develops_skills": []},
        {"prerequisites": {"missing": 1}},
        {"prerequisites": {"technical": 2}},
        {"format": "in_person", "upcoming_sessions": []},
        {"format": "live_online", "upcoming_sessions": ["2026-09-30"]},
    ],
)
def test_eligibility_rejects_each_ineligible_condition(changes):
    assert filter_eligible_events(employee(), [event(**changes)], [], SNAPSHOT_DATE) == []


def test_eligibility_includes_today_future_and_self_paced_without_sessions():
    activities = [
        event("TODAY", format="in_person", upcoming_sessions=["2026-10-01"]),
        event("FUTURE", format="live_online", upcoming_sessions=["2026-09-01", "2026-10-02"]),
        event("SELF", prerequisites={"technical": 1}),
    ]
    assert filter_eligible_events(employee(), activities, [], SNAPSHOT_DATE) == activities


def test_completed_history_is_employee_specific_and_recurring_club_is_repeatable():
    activities = [event(), event("EV_036"), event("OTHER_PERSON")]
    records = [
        history(),
        history("REC_CLUB", event_id="EV_036"),
        history("REC_OTHER", employee_id="SOMEONE_ELSE", event_id="OTHER_PERSON"),
    ]
    actual = filter_eligible_events(employee(), activities, records, SNAPSHOT_DATE)
    assert [item.event_id for item in actual] == ["EV_036", "OTHER_PERSON"]


def test_participation_counts_only_own_other_similar_events_and_separates_low_feedback():
    candidate = event()
    similar = event("SIMILAR")
    unrelated = event("UNRELATED", develops_skills=[{"skill_id": "other", "gain": 1, "max_level": 5}])
    records = [
        history("R1", event_id="SIMILAR", status="declined", feedback_rating=1),
        history("R2", event_id="SIMILAR", status="dropped"),
        history("R3", event_id="SIMILAR", status="no_show", feedback_rating=5),
        history("R4", event_id="SIMILAR", status="completed", feedback_rating=2),
        history("R5", event_id="SIMILAR", employee_id="OTHER", status="declined", feedback_rating=1),
        history("R6", status="declined", feedback_rating=1),
        history("R7", event_id="UNRELATED", status="declined", feedback_rating=1),
        history("R8", event_id="UNKNOWN", status="declined", feedback_rating=1),
    ]
    catalog = {item.event_id: item for item in [candidate, similar, unrelated]}
    assert compute_participation_factors("EMP_TEST", candidate, records, catalog) == (4.0, 3)
    assert compute_participation_penalty("EMP_TEST", candidate, records, catalog) == 4.0


def test_scoring_caps_gain_weights_critical_and_applies_bonus_once():
    person = employee()
    activity = event(develops_skills=[
        {"skill_id": "technical", "gain": 5, "max_level": 3},
        {"skill_id": "communication", "gain": 2, "max_level": 2},
    ])
    scored = score_event(person, activity, compute_skill_gaps(person, profile()), 1.0, past_declines_for_similar=1)
    assert scored.gap_before == {"technical": 2, "communication": 3}
    assert scored.gap_after == {"technical": 0, "communication": 2}
    assert scored.closes_skills == ["communication", "technical"]
    assert scored.critical is True
    assert scored.score == 5 - 1.5 + CRITICAL_BONUS
    assert scored.past_declines_for_similar == 1
    assert person.skills == {"technical": 1, "communication": 1}


def test_teaching_cap_below_existing_level_never_increases_gap_or_earns_bonus():
    person = employee(skills={"technical": 3})
    target = profile(required_skills={"technical": 5})
    activity = event(develops_skills=[{"skill_id": "technical", "gain": 2, "max_level": 2}])
    scored = score_event(person, activity, compute_skill_gaps(person, target), 0)
    assert scored.gap_before == scored.gap_after == {"technical": 2}
    assert scored.closes_skills == []
    assert scored.score == 0
    assert scored.critical is False
    assert recommend_next_steps(MemoryStore(person, [activity], target), person.employee_id) == []


def test_duplicate_skill_entries_cannot_close_more_than_the_gap():
    person = employee()
    activity = event(develops_skills=[
        {"skill_id": "technical", "gain": 2, "max_level": 3},
        {"skill_id": "technical", "gain": 2, "max_level": 3},
    ])
    scored = score_event(person, activity, compute_skill_gaps(person, profile()), 0)
    assert scored.score == 4 + CRITICAL_BONUS
    assert scored.gap_after == {"technical": 0}


def test_history_can_shift_priority_from_a_larger_soft_gap_to_a_critical_skill():
    person = employee()
    technical = event("TECHNICAL")
    soft = event("SOFT", develops_skills=[{"skill_id": "communication", "gain": 3, "max_level": 5}])
    past_soft = event("PAST_SOFT", mandatory=True, develops_skills=[{"skill_id": "communication", "gain": 1, "max_level": 5}])
    store = MemoryStore(person, [technical, soft, past_soft])
    assert recommend_next_steps(store, person.employee_id)[0].event_id == "SOFT"
    store.records = [
        history("R1", event_id="PAST_SOFT", status="declined"),
        history("R2", event_id="PAST_SOFT", status="no_show"),
    ]
    recommended = recommend_next_steps(store, person.employee_id)
    assert [item.event_id for item in recommended] == ["TECHNICAL", "SOFT"]
    assert recommended[1].past_declines_for_similar == 2


def test_recommendations_use_same_role_next_grade_and_stable_ties():
    person = employee(career_goal={"target_role": "Manager", "target_grade": "Lead"})
    store = MemoryStore(person, [event("B"), event("A"), event("C")])
    recommended = recommend_next_steps(store, person.employee_id, top_n=2)
    assert [item.event_id for item in recommended] == ["A", "B"]
    assert recommend_next_steps(store, person.employee_id, top_n=0) == []
    with pytest.raises(ValueError, match="top_n"):
        recommend_next_steps(store, person.employee_id, top_n=-1)
    with pytest.raises(ValueError, match="Unknown employee"):
        recommend_next_steps(store, "UNKNOWN")


@pytest.mark.parametrize("person", [employee(grade="Lead"), employee(skills={"technical": 5, "communication": 5})])
def test_top_grade_or_no_remaining_gaps_returns_no_recommendations(person):
    assert recommend_next_steps(MemoryStore(person, [event()]), person.employee_id) == []


def test_low_feedback_penalty_never_fabricates_past_declines():
    person = employee()
    store = MemoryStore(person, [event(), event("OTHER", mandatory=True)], records=[
        history(event_id="OTHER", feedback_rating=1)
    ])
    scored = recommend_next_steps(store, person.employee_id)[0]
    assert scored.past_declines_for_similar == 0
    assert scored.score == 2 - 1.5 * 0.5
