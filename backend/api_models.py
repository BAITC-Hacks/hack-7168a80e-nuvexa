"""Public response and bulk-import schemas for frontend integration."""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from backend.models import ActivityRecord, Employee, Grade, SkillGap


class HistoryItem(ActivityRecord):
    event_title: str


class EmployeeDetail(Employee):
    activity_history: list[HistoryItem]
    next_grade: Grade | None
    skill_gaps: list[SkillGap]


class Recommendation(BaseModel):
    event_id: str
    title: str
    rationale: str
    score: float
    closes_skills: list[str]
    critical: bool
    duration_hours: float
    format: str


class RecommendationsResponse(BaseModel):
    employee_id: str
    recommendations: list[Recommendation]


class CompletionResponse(RecommendationsResponse):
    event_id: str
    skills: dict[str, int]


class HRSkillGap(BaseModel):
    skill_id: str
    skill_name: str
    total_gap: int
    employees_affected: int


class EmployeeSummary(BaseModel):
    employee_id: str
    full_name: str
    role: str
    grade: Grade


class ParticipationStats(BaseModel):
    event_id: str
    title: str
    completed: int = 0
    declined: int = 0
    no_show: int = 0
    dropped: int = 0
    in_progress: int = 0
    overdue: int = 0
    total: int = 0


class BulkImport(BaseModel):
    model_config = ConfigDict(extra="forbid")
    employees: list[Employee] = Field(default_factory=list, max_length=10000)
    history: list[ActivityRecord] = Field(default_factory=list, max_length=50000)


class FileImport(BaseModel):
    """Accept the import screen's parsed employees JSON or raw activity CSV."""

    model_config = ConfigDict(extra="forbid")
    type: Literal["employees", "history"]
    data: str | list[dict[str, Any]] | dict[str, Any]


class ImportResponse(BaseModel):
    employees_imported: int
    history_imported: int
    message: str
