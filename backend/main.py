"""FastAPI endpoints for the Career Quest employee and HR workflows."""

import asyncio
import json
import logging
from collections import defaultdict
from contextlib import asynccontextmanager
from io import StringIO
from typing import Annotated, Any

import httpx
from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from backend.api_models import (
    BulkImport,
    CompletionResponse,
    EmployeeDetail,
    EmployeeSummary,
    FileImport,
    HRSkillGap,
    ImportResponse,
    ParticipationStats,
    Recommendation,
    RecommendationsResponse,
)
from backend.config import SNAPSHOT_DATE, Settings
from backend.data_store import AlreadyCompletedError, DataStore, parse_history_csv
from backend.models import Employee, ScoredEvent, Skill
from backend.rationale_generator import explain_recommendation
from backend.recommendation_engine import compute_skill_gaps, recommend_next_steps

logger = logging.getLogger(__name__)


def get_data_store(request: Request) -> DataStore:
    """Return the singleton created during this application's startup."""
    return request.app.state.data_store


StoreDependency = Annotated[DataStore, Depends(get_data_store)]


def require_employee(store: DataStore, employee_id: str) -> Employee:
    employee = store.get_employee(employee_id)
    if employee is None:
        raise HTTPException(404, f"Unknown employee_id: {employee_id}")
    return employee


async def _explain(
    request: Request, employee: Employee, scored: list[ScoredEvent]
) -> list[Recommendation]:
    settings = request.app.state.settings
    # Each call has a hard <=6s deadline, and gather starts all three together.
    # No store locks are held during network I/O.
    rationales = await asyncio.gather(
        *[
            explain_recommendation(
                request.app.state.llm_client,
                employee,
                event,
                model=settings.llm_model,
                timeout_seconds=settings.llm_timeout_seconds,
            )
            for event in scored
        ]
    )
    return [
        Recommendation(
            event_id=event.event_id,
            title=event.event_title,
            rationale=rationale,
            score=event.score,
            closes_skills=event.closes_skills,
            critical=event.critical,
            duration_hours=event.duration_hours,
            format=event.format,
        )
        for event, rationale in zip(scored, rationales, strict=True)
    ]


def _file_import(payload: FileImport) -> tuple[list[dict], list[dict]]:
    if payload.type == "history" and isinstance(payload.data, str):
        return [], parse_history_csv(StringIO(payload.data))
    value = json.loads(payload.data) if isinstance(payload.data, str) else payload.data
    if isinstance(value, dict):
        field = "employees" if payload.type == "employees" else "history"
        if field not in value or set(value) - {field, "meta"}:
            raise ValueError(f"Import JSON must contain '{field}' and optional 'meta'.")
        value = value[field]
    if not isinstance(value, list) or any(not isinstance(item, dict) for item in value):
        raise ValueError("Import data must be a list of record objects.")
    return (value, []) if payload.type == "employees" else ([], value)


def create_app(settings: Settings | None = None, data_store: DataStore | None = None) -> FastAPI:
    """Create an isolated app; dataset loading and HTTP clients belong to lifespan."""
    settings = settings or Settings.from_env()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.settings = settings
        app.state.data_store = data_store or DataStore(settings.data_dir)
        if app.state.data_store.synthetic:
            logger.warning(
                "Career Quest is using synthetic data from %s.",
                app.state.data_store.data_dir,
            )
        app.state.llm_client = None
        if settings.llm_api_key:
            app.state.llm_client = httpx.AsyncClient(
                base_url=settings.llm_base_url.rstrip("/") + "/",
                headers={"Authorization": f"Bearer {settings.llm_api_key}"},
                timeout=settings.llm_timeout_seconds,
                limits=httpx.Limits(max_connections=20, max_keepalive_connections=10),
            )
        try:
            yield
        finally:
            if app.state.llm_client is not None:
                await app.state.llm_client.aclose()

    app = FastAPI(title="Career Quest API", version="1.0.0", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.cors_origins),
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type"],
    )

    @app.exception_handler(HTTPException)
    async def http_error(_request: Request, exc: HTTPException):
        return JSONResponse(
            status_code=exc.status_code, content={"detail": exc.detail, "message": str(exc.detail)}
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error(_request: Request, exc: RequestValidationError):
        errors = [{key: error[key] for key in ("loc", "msg", "type")} for error in exc.errors()]
        return JSONResponse(
            status_code=422, content={"detail": errors, "message": "Request validation failed."}
        )

    @app.get("/health", tags=["System"])
    def health(store: StoreDependency) -> dict[str, Any]:
        with store.lock:
            return {
                "status": "ok",
                "snapshot_date": SNAPSHOT_DATE.isoformat(),
                "synthetic_data": store.synthetic,
                "employees": len(store.employees),
                "events": len(store.events),
                "history_records": len(store.activity_history),
                "rationale_mode": "llm_with_fallback" if settings.llm_api_key else "template",
            }

    @app.get("/employees/{employee_id}", response_model=EmployeeDetail, tags=["Employee"])
    def get_employee(employee_id: str, store: StoreDependency):
        with store.lock:
            employee = require_employee(store, employee_id)
            next_grade = store.get_next_grade(employee.role, employee.grade)
            profile = store.get_role_profile(employee.role, next_grade) if next_grade else None
            return {
                **employee.model_dump(),
                "next_grade": next_grade,
                "skill_gaps": compute_skill_gaps(employee, profile) if profile else [],
                "activity_history": [
                    {**record.model_dump(), "event_title": store.events[record.event_id].title}
                    for record in sorted(
                        store.get_employee_history(employee_id),
                        key=lambda r: (r.date, r.record_id),
                        reverse=True,
                    )
                ],
            }

    @app.get("/skills", response_model=list[Skill], tags=["Catalog"])
    def get_skills(store: StoreDependency):
        return list(store.skills.values())

    @app.get(
        "/employees/{employee_id}/recommendations",
        response_model=RecommendationsResponse,
        tags=["Employee"],
    )
    async def recommendations(
        employee_id: str,
        request: Request,
        store: StoreDependency,
        top_n: Annotated[int, Query(ge=1, le=3)] = 3,
    ):
        with store.lock:
            employee = require_employee(store, employee_id)
            scored = recommend_next_steps(store, employee_id, top_n=top_n)
        return RecommendationsResponse(
            employee_id=employee_id, recommendations=await _explain(request, employee, scored)
        )

    @app.post(
        "/employees/{employee_id}/activities/{event_id}/complete",
        response_model=CompletionResponse,
        tags=["Employee"],
    )
    async def complete(employee_id: str, event_id: str, request: Request, store: StoreDependency):
        with store.lock:
            require_employee(store, employee_id)
            if event_id not in store.events:
                raise HTTPException(404, f"Unknown event_id: {event_id}")
            try:
                employee = store.complete_activity(employee_id, event_id)
            except AlreadyCompletedError as exc:
                raise HTTPException(409, str(exc)) from exc
            scored = recommend_next_steps(store, employee_id)
        return CompletionResponse(
            employee_id=employee_id,
            event_id=event_id,
            skills=employee.skills,
            recommendations=await _explain(request, employee, scored),
        )

    @app.get("/hr/skill-gaps", response_model=list[HRSkillGap], tags=["HR"])
    def hr_skill_gaps(store: StoreDependency):
        totals: dict[str, list[int]] = defaultdict(lambda: [0, 0])
        # At production scale cache these aggregates, invalidated by completion/import.
        with store.lock:
            for employee in store.employees.values():
                next_grade = store.get_next_grade(employee.role, employee.grade)
                profile = store.get_role_profile(employee.role, next_grade) if next_grade else None
                if profile:
                    for gap in compute_skill_gaps(employee, profile):
                        if gap.gap > 0:
                            totals[gap.skill_id][0] += gap.gap
                            totals[gap.skill_id][1] += 1
        return [
            HRSkillGap(
                skill_id=key,
                skill_name=store.skills[key].name,
                total_gap=value[0],
                employees_affected=value[1],
            )
            for key, value in sorted(totals.items(), key=lambda item: (-item[1][0], item[0]))[:15]
        ]

    @app.get(
        "/hr/employees-without-recommendation", response_model=list[EmployeeSummary], tags=["HR"]
    )
    def hr_without_recommendation(store: StoreDependency):
        with store.lock:
            return [
                EmployeeSummary(
                    **employee.model_dump(include={"employee_id", "full_name", "role", "grade"})
                )
                for employee in sorted(
                    store.employees.values(), key=lambda employee: employee.employee_id
                )
                if not recommend_next_steps(store, employee.employee_id)
            ]

    @app.get("/hr/participation-stats", response_model=list[ParticipationStats], tags=["HR"])
    def hr_participation(store: StoreDependency):
        with store.lock:
            counts = store.activity_history.groupby(["event_id", "status"]).size()
            events: dict[str, ParticipationStats] = {}
            for (event_id, status), count in counts.items():
                row = events.setdefault(
                    event_id,
                    ParticipationStats(event_id=event_id, title=store.events[event_id].title),
                )
                setattr(row, status, int(count))
                row.total += int(count)
            return sorted(events.values(), key=lambda row: (-row.total, row.event_id))

    @app.post("/data/import", response_model=ImportResponse, tags=["Import"])
    def import_data(payload: BulkImport | FileImport, store: StoreDependency):
        try:
            if isinstance(payload, BulkImport):
                employees = [employee.model_dump() for employee in payload.employees]
                history = [record.model_dump() for record in payload.history]
            else:
                employees, history = _file_import(payload)
            if not employees and not history:
                raise ValueError("Provide at least one employee or activity history record.")
            counts = store.import_data(employees, history)
        except ValidationError as exc:
            errors = [{key: error[key] for key in ("loc", "msg", "type")} for error in exc.errors()]
            return JSONResponse(
                status_code=422,
                content={
                    "detail": errors,
                    "message": "Import validation failed; no records changed.",
                },
            )
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        return ImportResponse(**counts, message="Data imported successfully into memory.")

    return app


app = create_app()
