"""Validated data contracts shared by the API, data loader, and scoring engine."""

from datetime import date
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

NonEmptyString = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
SkillLevel = Annotated[int, Field(ge=0, le=5, strict=True)]
NonNegativeInteger = Annotated[int, Field(ge=0, strict=True)]
Percentage = Annotated[float, Field(ge=0, le=100, allow_inf_nan=False)]
Grade = Literal["Junior", "Middle", "Senior", "Lead"]
ActivityStatus = Literal[
    "completed", "in_progress", "dropped", "no_show", "declined", "overdue"
]


class SchemaModel(BaseModel):
    """Reject misspelled/unknown fields rather than silently discarding input."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)


class CareerGoal(SchemaModel):
    """An employee's stated longer-term destination."""

    target_role: NonEmptyString
    target_grade: Grade


class Employee(SchemaModel):
    """Employee profile from employees.json."""

    employee_id: NonEmptyString
    full_name: NonEmptyString
    department: NonEmptyString
    role: NonEmptyString
    grade: Grade
    manager_id: NonEmptyString | None = None
    hire_date: date
    tenure_months: NonNegativeInteger
    work_format: NonEmptyString
    preferred_language: Literal["kk", "ru", "en"]
    career_goal: CareerGoal | None = None
    skills: dict[NonEmptyString, SkillLevel]
    last_review_date: date | None = None


class Skill(SchemaModel):
    """A skill catalog entry; catalog categories remain extensible."""

    skill_id: NonEmptyString
    name: NonEmptyString
    type: NonEmptyString
    category: NonEmptyString
    description: NonEmptyString


class RoleProfile(SchemaModel):
    """Required proficiency and critical skills for a role at a specific grade."""

    role: NonEmptyString
    grade: Grade
    required_skills: dict[NonEmptyString, SkillLevel]
    critical_skills: list[NonEmptyString]


class SkillDevelopment(SchemaModel):
    """One activity's improvement and the highest level it can teach."""

    skill_id: NonEmptyString
    gain: SkillLevel
    max_level: SkillLevel


class Event(SchemaModel):
    """A learning activity and its participation constraints."""

    event_id: NonEmptyString
    title: NonEmptyString
    description: NonEmptyString
    type: NonEmptyString
    format: NonEmptyString
    duration_hours: Annotated[float, Field(gt=0, allow_inf_nan=False)]
    mandatory: bool
    target_roles: list[NonEmptyString]
    target_grades: list[Grade]
    develops_skills: list[SkillDevelopment]
    prerequisites: dict[NonEmptyString, SkillLevel]
    upcoming_sessions: list[date]


class ActivityRecord(SchemaModel):
    """One historical participation record, including nullable CSV values."""

    record_id: NonEmptyString
    employee_id: NonEmptyString
    event_id: NonEmptyString
    date: date
    due_date: date | None = None
    status: ActivityStatus
    completion_pct: Percentage
    score: Percentage | None = None
    feedback_rating: Annotated[int, Field(ge=1, le=5, strict=True)] | None = None
    assigned_by: NonEmptyString


class SkillGap(SchemaModel):
    """A positive proficiency deficit relative to the next grade."""

    skill_id: NonEmptyString
    current_level: SkillLevel
    required_level: SkillLevel
    gap: SkillLevel
    weighted_gap: Annotated[int, Field(ge=0, le=10, strict=True)]
    critical: bool


class ScoredEvent(SchemaModel):
    """Deterministic recommendation facts consumed by rationale generation."""

    event_id: NonEmptyString
    event_title: NonEmptyString
    score: Annotated[float, Field(allow_inf_nan=False)]
    closes_skills: list[NonEmptyString]
    gap_before: dict[NonEmptyString, SkillLevel]
    gap_after: dict[NonEmptyString, SkillLevel]
    critical: bool
    past_declines_for_similar: NonNegativeInteger
    duration_hours: Annotated[float, Field(gt=0, allow_inf_nan=False)]
    format: NonEmptyString
