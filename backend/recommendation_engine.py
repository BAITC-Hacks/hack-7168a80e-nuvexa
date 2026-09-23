"""Pure, deterministic recommendation scoring; this module performs no I/O."""

from datetime import date
from typing import TYPE_CHECKING

from .config import SNAPSHOT_DATE
from .models import ActivityRecord, Employee, Event, RoleProfile, ScoredEvent, SkillGap

if TYPE_CHECKING:
    from .data_store import DataStore


# Promotion-critical skills count twice because they are explicit progression blockers.
CRITICAL_SKILL_WEIGHT = 2
# One negative participation weighs less than one critical level but more than one ordinary level.
PENALTY_WEIGHT = 1.5
# Fully resolving a critical requirement earns a small, one-time preference over partial progress.
CRITICAL_BONUS = 1.0
# A refusal, missed session, or dropout is direct evidence of poor fit.
NEGATIVE_PARTICIPATION_PENALTY = 1.0
# Low feedback is a weaker signal than opting out, so it receives half the penalty.
LOW_FEEDBACK_PENALTY = 0.5
RECURRING_EVENT_ID = "EV_036"
NEGATIVE_PARTICIPATION_STATUSES = frozenset({"declined", "no_show", "dropped"})


def compute_skill_gaps(employee: Employee, role_profile: RoleProfile) -> list[SkillGap]:
    """Return positive next-grade gaps, weighted by importance and stably sorted."""
    if employee.grade == "Lead":
        return []
    critical_skills = set(role_profile.critical_skills)
    gaps = []
    for skill_id, required_level in role_profile.required_skills.items():
        current_level = employee.skills.get(skill_id, 0)
        gap = max(0, required_level - current_level)
        if gap == 0:
            continue
        critical = skill_id in critical_skills
        gaps.append(
            SkillGap(
                skill_id=skill_id,
                current_level=current_level,
                required_level=required_level,
                gap=gap,
                weighted_gap=gap * (CRITICAL_SKILL_WEIGHT if critical else 1),
                critical=critical,
            )
        )
    return sorted(gaps, key=lambda gap: (-gap.weighted_gap, gap.skill_id))


def filter_eligible_events(
    employee: Employee,
    events: list[Event],
    history: list[ActivityRecord],
    today: date,
) -> list[Event]:
    """Apply role, grade, learning value, completion, prerequisite and session rules."""
    completed = {
        record.event_id
        for record in history
        if record.employee_id == employee.employee_id and record.status == "completed"
    }
    eligible = []
    for event in events:
        if employee.role not in event.target_roles or employee.grade not in event.target_grades:
            continue
        if event.mandatory or not event.develops_skills:
            continue
        if event.event_id in completed and event.event_id != RECURRING_EVENT_ID:
            continue
        if any(employee.skills.get(skill_id, 0) < level for skill_id, level in event.prerequisites.items()):
            continue
        if event.format != "self_paced" and not any(session >= today for session in event.upcoming_sessions):
            continue
        eligible.append(event)
    return eligible


def compute_participation_factors(
    employee_id: str,
    event: Event,
    history: list[ActivityRecord],
    all_events: dict[str, Event],
) -> tuple[float, int]:
    """Return weighted history penalty and the separate factual negative-status count."""
    skill_ids = {development.skill_id for development in event.develops_skills}
    similar_ids = {
        other_id
        for other_id, other_event in all_events.items()
        if other_id != event.event_id
        and any(development.skill_id in skill_ids for development in other_event.develops_skills)
    }
    negative_count = 0
    low_feedback_count = 0
    for record in history:
        if record.employee_id != employee_id or record.event_id not in similar_ids:
            continue
        if record.status in NEGATIVE_PARTICIPATION_STATUSES:
            negative_count += 1
        if record.feedback_rating is not None and record.feedback_rating <= 2:
            low_feedback_count += 1
    return (
        negative_count * NEGATIVE_PARTICIPATION_PENALTY
        + low_feedback_count * LOW_FEEDBACK_PENALTY,
        negative_count,
    )


def compute_participation_penalty(
    employee_id: str,
    event: Event,
    history: list[ActivityRecord],
    all_events: dict[str, Event],
) -> float:
    """Penalize negative participation (1.0) and low feedback (0.5) on similar events."""
    penalty, _ = compute_participation_factors(employee_id, event, history, all_events)
    return penalty


def score_event(
    employee: Employee,
    event: Event,
    gaps: list[SkillGap],
    penalty: float,
    *,
    past_declines_for_similar: int = 0,
) -> ScoredEvent:
    """Score actual capped improvement, keeping numeric rationale facts explicit.

    A penalty cannot reveal the number of declines because it also contains ratings;
    callers with history supply that independent count through the keyword argument.
    """
    gap_by_skill = {gap.skill_id: gap for gap in gaps if gap.gap > 0}
    gap_before: dict[str, int] = {}
    gap_after: dict[str, int] = {}
    for development in event.develops_skills:
        gap = gap_by_skill.get(development.skill_id)
        if gap is None:
            continue
        skill_id = gap.skill_id
        gap_before.setdefault(skill_id, gap.gap)
        remaining_gap = gap_after.get(skill_id, gap.gap)
        already_closed = gap.gap - remaining_gap
        current_level = employee.skills.get(skill_id, 0) + already_closed
        # A teaching cap below the employee's existing level must never reduce proficiency.
        teachable_gain = max(0, development.max_level - current_level)
        closed = min(remaining_gap, development.gain, teachable_gain)
        gap_after[skill_id] = remaining_gap - closed

    closes_skills = sorted(
        skill_id for skill_id in gap_before if gap_after[skill_id] < gap_before[skill_id]
    )
    weighted_closed = sum(
        (gap_before[skill_id] - gap_after[skill_id])
        * (CRITICAL_SKILL_WEIGHT if gap_by_skill[skill_id].critical else 1)
        for skill_id in closes_skills
    )
    critical = any(gap_by_skill[skill_id].critical for skill_id in closes_skills)
    resolves_critical = any(
        gap_by_skill[skill_id].critical and gap_after[skill_id] == 0
        for skill_id in closes_skills
    )
    score = weighted_closed - PENALTY_WEIGHT * penalty
    if resolves_critical:
        score += CRITICAL_BONUS
    return ScoredEvent(
        event_id=event.event_id,
        event_title=event.title,
        score=score,
        closes_skills=closes_skills,
        gap_before=gap_before,
        gap_after=gap_after,
        critical=critical,
        past_declines_for_similar=past_declines_for_similar,
        duration_hours=event.duration_hours,
        format=event.format,
    )


def recommend_next_steps(
    data_store: "DataStore",
    employee_id: str,
    top_n: int = 3,
    today: date | None = None,
) -> list[ScoredEvent]:
    """Recommend useful eligible activities for the next grade in the same role."""
    if top_n < 0:
        raise ValueError("top_n must be nonnegative")
    employee = data_store.get_employee(employee_id)
    if employee is None:
        raise ValueError(f"Unknown employee: {employee_id}")
    if top_n == 0:
        return []
    next_grade = data_store.get_next_grade(employee.role, employee.grade)
    if next_grade is None:
        return []
    role_profile = data_store.get_role_profile(employee.role, next_grade)
    if role_profile is None:
        return []
    gaps = compute_skill_gaps(employee, role_profile)
    if not gaps:
        return []
    history = data_store.get_employee_history(employee_id)
    events = filter_eligible_events(
        employee, list(data_store.events.values()), history, today or SNAPSHOT_DATE
    )
    recommendations = []
    for event in events:
        penalty, negative_count = compute_participation_factors(
            employee_id, event, history, data_store.events
        )
        scored = score_event(
            employee, event, gaps, penalty, past_declines_for_similar=negative_count
        )
        # A history adjustment or bonus never makes an activity with zero skill benefit useful.
        if scored.closes_skills:
            recommendations.append(scored)
    recommendations.sort(key=lambda recommendation: (-recommendation.score, recommendation.event_id))
    return recommendations[:top_n]
