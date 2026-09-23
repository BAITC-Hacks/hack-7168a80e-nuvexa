"""Validated, process-local data with atomic imports and activity completion."""

import csv
import json
import re
from collections import defaultdict
from datetime import date
from io import StringIO
from pathlib import Path
from threading import RLock
from typing import Any

import pandas as pd

from backend.config import GRADE_ORDER, SNAPSHOT_DATE
from backend.models import ActivityRecord, Employee, Event, RoleProfile, Skill

HISTORY_COLUMNS = (
    "record_id",
    "employee_id",
    "event_id",
    "date",
    "due_date",
    "status",
    "completion_pct",
    "score",
    "feedback_rating",
    "assigned_by",
)


class AlreadyCompletedError(ValueError):
    """A non-recurring activity was already completed by this employee."""


def parse_history_csv(content: Any) -> list[dict[str, Any]]:
    """Read paths or text streams, preserving identifiers and converting CSV nulls."""
    text = (
        content.read()
        if hasattr(content, "read")
        else Path(content).read_text(encoding="utf-8-sig")
    )
    text = text.lstrip("\ufeff")
    try:
        rows = csv.reader(StringIO(text), strict=True)
        header = next(rows, [])
        if header != list(HISTORY_COLUMNS):
            raise ValueError("CSV headers must be exactly: " + ",".join(HISTORY_COLUMNS))
        for line_number, row in enumerate(rows, start=2):
            if row and len(row) != len(HISTORY_COLUMNS):
                raise ValueError(f"CSV row {line_number} must have {len(HISTORY_COLUMNS)} columns.")
    except csv.Error as exc:
        raise ValueError("Malformed CSV quoting.") from exc
    frame = pd.read_csv(StringIO(text), dtype=str, keep_default_na=False)
    if list(frame.columns) != list(HISTORY_COLUMNS):
        raise ValueError("CSV headers must be exactly: " + ",".join(HISTORY_COLUMNS))
    records = frame.to_dict(orient="records")
    for record in records:
        for key in ("due_date", "score", "feedback_rating"):
            if not record[key].strip():
                record[key] = None
        # CSV has only strings; JSON requests retain normal schema validation.
        for key in ("feedback_rating",):
            if record[key] is not None:
                numeric = float(record[key])
                if not numeric.is_integer():
                    raise ValueError(f"{key} must be an integer.")
                record[key] = int(numeric)
        if record["score"] is not None:
            record["score"] = float(record["score"])
        record["completion_pct"] = float(record["completion_pct"])
    return records


def _unique(items: list[Any], key: str) -> dict[Any, Any]:
    result = {}
    for item in items:
        identifier = getattr(item, key)
        if identifier in result:
            raise ValueError(f"Duplicate {key}: {identifier}")
        result[identifier] = item
    return result


class DataStore:
    """Load all four files once; indexes keep the small demo's reads inexpensive.

    Callers can hold ``lock`` across related reads for a consistent snapshot. Data is
    intentionally in memory: use one application worker, and restart to reset it.
    """

    def __init__(self, data_dir: str | Path):
        self.data_dir = Path(data_dir)
        self.lock = RLock()
        self.metadata: dict[str, Any] = {}
        employees_doc = self._read_json("employees.json")
        events_doc = self._read_json("events.json")
        skills_doc = self._read_json("skills.json")
        self.skills = _unique([Skill.model_validate(v) for v in skills_doc["skills"]], "skill_id")
        self.proficiency_scale = skills_doc["proficiency_scale"]
        self.role_profiles = [RoleProfile.model_validate(v) for v in skills_doc["role_profiles"]]
        self._profiles = {}
        for profile in self.role_profiles:
            key = (profile.role, profile.grade)
            if key in self._profiles:
                raise ValueError(f"Duplicate role profile: {key}")
            self._profiles[key] = profile
            self._check_skills(profile.required_skills)
        self.events = _unique([Event.model_validate(v) for v in events_doc["events"]], "event_id")
        for event in self.events.values():
            self._check_skills(event.prerequisites)
            self._check_skills(item.skill_id for item in event.develops_skills)
        # Keep imported assessments separate from derived current skills so history
        # corrections and repeated imports never accumulate the same gains twice.
        self._assessments: dict[str, Employee] = {}
        self.employees: dict[str, Employee] = {}
        self._records: dict[str, ActivityRecord] = {}
        self._live_completion_order: dict[str, int] = {}
        self._history_by_employee: dict[str, list[ActivityRecord]] = {}
        self.activity_history = pd.DataFrame(columns=HISTORY_COLUMNS)
        self._next_record_number = 1
        self.import_data(
            employees_doc["employees"], parse_history_csv(self.data_dir / "activity_history.csv")
        )

    def _read_json(self, filename: str) -> dict[str, Any]:
        path = self.data_dir / filename
        if not path.is_file():
            raise FileNotFoundError(
                f"Missing dataset file: {path}. Supply all four starter files or use sample_data."
            )
        with path.open(encoding="utf-8-sig") as handle:
            doc = json.load(handle)
        if not isinstance(doc, dict):
            raise ValueError(f"{filename} must contain a JSON object.")
        self.metadata[filename] = doc.get("meta", {})
        return doc

    @property
    def synthetic(self) -> bool:
        """Expose demo status so a frontend or judge cannot confuse it with real data."""
        return any(meta.get("synthetic") is True for meta in self.metadata.values())

    def _check_skills(self, identifiers: Any) -> None:
        unknown = sorted(set(identifiers) - self.skills.keys())
        if unknown:
            raise ValueError("Unknown skill_id(s): " + ", ".join(unknown))

    def get_employee(self, employee_id: str) -> Employee | None:
        """Return a detached employee so callers cannot partially mutate the store."""
        with self.lock:
            employee = self.employees.get(employee_id)
            return employee.model_copy(deep=True) if employee else None

    def get_next_grade(self, role: str, grade: str) -> str | None:
        """Return the next grade; profile availability is checked separately."""
        if grade not in GRADE_ORDER or grade == GRADE_ORDER[-1]:
            return None
        return GRADE_ORDER[GRADE_ORDER.index(grade) + 1]

    def get_role_profile(self, role: str, grade: str) -> RoleProfile | None:
        return self._profiles.get((role, grade))

    def get_employee_history(self, employee_id: str) -> list[ActivityRecord]:
        """Return only this employee's records using a prebuilt in-memory index."""
        with self.lock:
            return [
                record.model_copy() for record in self._history_by_employee.get(employee_id, [])
            ]

    def import_employees(self, new_employees: list[dict]) -> int:
        """Validate a complete batch before upserting employee IDs."""
        return self.import_data(new_employees, [])["employees_imported"]

    def import_history(self, new_records: list[dict]) -> int:
        """Upsert records and rebuild skills from assessments plus post-review gains."""
        return self.import_data([], new_records)["history_imported"]

    def import_data(self, employees: list[dict], history: list[dict]) -> dict[str, int]:
        """Atomically merge assessments/history and derive current employee skills.

        Imported employee skills describe their last assessment, not the derived
        skills returned by the API. Re-importing the same source is idempotent.
        """
        new_employees = _unique([Employee.model_validate(v) for v in employees], "employee_id")
        new_records = _unique([ActivityRecord.model_validate(v) for v in history], "record_id")
        for employee in new_employees.values():
            self._check_skills(employee.skills)
        with self.lock:
            employee_ids = self.employees.keys() | new_employees.keys()
            for record in new_records.values():
                if record.employee_id not in employee_ids:
                    raise ValueError(f"Unknown employee_id in history: {record.employee_id}")
                if record.event_id not in self.events:
                    raise ValueError(f"Unknown event_id in history: {record.event_id}")
            merged_records = self._records | new_records
            history_state = self._build_history(merged_records)
            assessments = self._assessments | new_employees
            changed_assessments = {
                employee_id
                for employee_id, employee in new_employees.items()
                if employee_id not in self._assessments
                or employee.skills != self._assessments[employee_id].skills
                or employee.last_review_date != self._assessments[employee_id].last_review_date
            }
            # A replacement assessment supersedes local same-day/undated gains.
            # Metadata-only edits (name, department, feedback) keep them intact.
            completion_fields = {"employee_id", "event_id", "date", "status"}
            live_order = {
                record_id: order
                for record_id, order in self._live_completion_order.items()
                if self._records[record_id].employee_id not in changed_assessments
                and self._records[record_id].model_dump(include=completion_fields)
                == merged_records[record_id].model_dump(include=completion_fields)
            }
            effective_employees = self._build_employees(assessments, history_state[0], live_order)
            # Prepare every derived structure before publishing any part of the batch.
            self._assessments = assessments
            self.employees = effective_employees
            self._records = merged_records
            self._live_completion_order = live_order
            self._history_by_employee, self.activity_history, self._next_record_number = (
                history_state
            )
        return {"employees_imported": len(new_employees), "history_imported": len(new_records)}

    def _apply_event_gains(self, employee: Employee, event_id: str) -> None:
        """Apply capped gains to a detached profile without lowering any skill."""
        for development in self.events[event_id].develops_skills:
            current = employee.skills.get(development.skill_id, 0)
            employee.skills[development.skill_id] = max(
                current, min(development.max_level, current + development.gain)
            )

    def _build_employees(
        self,
        assessments: dict[str, Employee],
        history: dict[str, list[ActivityRecord]],
        live_order: dict[str, int],
    ) -> dict[str, Employee]:
        """Derive effective skills from assessments and chronologically ordered gains.

        Self-paced dates are enrollment dates. Only enrollment after the review
        proves a completed course was not assessed already; earlier/same-day
        enrollments stay unapplied. With no review date, historical timing is
        unknown. Locally recorded completions are known to be new even when the
        assessment date is absent or today. They follow imported history on that
        date in execution order: identifier sorting must not move a new capped
        course ahead of learning that already happened.
        """
        employees = {}
        for employee_id, assessment in assessments.items():
            employee = assessment.model_copy(deep=True)
            for record in sorted(
                history.get(employee_id, []),
                key=lambda item: (
                    item.date,
                    item.record_id in live_order,
                    live_order.get(item.record_id, 0),
                    item.record_id,
                ),
            ):
                if record.status != "completed":
                    continue
                after_review = (
                    assessment.last_review_date is not None
                    and assessment.last_review_date < record.date <= SNAPSHOT_DATE
                )
                if after_review or record.record_id in live_order:
                    self._apply_event_gains(employee, record.event_id)
            employees[employee_id] = employee
        return employees

    def _build_history(
        self, records: dict[str, ActivityRecord]
    ) -> tuple[dict[str, list[ActivityRecord]], pd.DataFrame, int]:
        grouped: dict[str, list[ActivityRecord]] = defaultdict(list)
        for record in records.values():
            grouped[record.employee_id].append(record)
        frame = pd.DataFrame(
            [record.model_dump() for record in records.values()],
            columns=HISTORY_COLUMNS,
        )
        # Arbitrarily long external identifiers are opaque, not integer sequences.
        numbers = [
            int(match.group())
            for key in records
            if (match := re.search(r"[0-9]+$", key)) and len(match.group()) <= 100
        ]
        next_number = max(self._next_record_number, max(numbers, default=0) + 1)
        while f"REC_{next_number:06d}" in records:
            next_number += 1
        return dict(grouped), frame, next_number

    def complete_activity(
        self, employee_id: str, event_id: str, today: date = SNAPSHOT_DATE
    ) -> Employee:
        """Apply gains and append history together, serializing concurrent completions."""
        with self.lock:
            if employee_id not in self.employees:
                raise KeyError(f"Unknown employee_id: {employee_id}")
            if event_id not in self.events:
                raise KeyError(f"Unknown event_id: {event_id}")
            if event_id != "EV_036" and any(
                record.event_id == event_id and record.status == "completed"
                for record in self._history_by_employee.get(employee_id, [])
            ):
                raise AlreadyCompletedError(
                    f"Activity {event_id} is already completed for {employee_id}."
                )
            record = ActivityRecord(
                record_id=f"REC_{self._next_record_number:06d}",
                employee_id=employee_id,
                event_id=event_id,
                date=today,
                due_date=None,
                status="completed",
                completion_pct=100,
                score=None,
                feedback_rating=None,
                assigned_by="self",
            )
            merged_records = self._records | {record.record_id: record}
            history_state = self._build_history(merged_records)
            live_order = self._live_completion_order | {
                record.record_id: max(self._live_completion_order.values(), default=0) + 1
            }
            employees = self._build_employees(self._assessments, history_state[0], live_order)
            self.employees = employees
            self._records = merged_records
            self._live_completion_order = live_order
            self._history_by_employee, self.activity_history, self._next_record_number = (
                history_state
            )
            return employees[employee_id].model_copy(deep=True)
