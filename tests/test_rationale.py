"""Fast, offline checks for rationale grounding and provider failure handling."""

import asyncio
import json

import httpx
import pytest

from backend.models import Employee, ScoredEvent
from backend.rationale_generator import (
    build_rationale_prompt,
    explain_recommendation,
    fallback_rationale,
)


@pytest.fixture
def employee():
    return Employee(
        employee_id="EMP_001",
        full_name="Private Employee Name",
        department="Private Department",
        role="Data Analyst",
        grade="Junior",
        manager_id=None,
        hire_date="2025-01-01",
        tenure_months=21,
        work_format="hybrid",
        preferred_language="en",
        career_goal=None,
        skills={"SK_001": 1},
        last_review_date="2026-06-01",
    )


@pytest.fixture
def event():
    return ScoredEvent(
        event_id="EV_001",
        event_title="Useful activity",
        score=3.0,
        closes_skills=["SK_001"],
        gap_before={"SK_001": 2},
        gap_after={"SK_001": 1},
        critical=True,
        past_declines_for_similar=0,
        duration_hours=4,
        format="online",
    )


def call_provider(employee, event, handler, *, timeout_seconds=0.2):
    async def run():
        async with httpx.AsyncClient(
            base_url="https://provider.invalid/v1/",
            transport=httpx.MockTransport(handler),
        ) as client:
            return await explain_recommendation(
                client, employee, event, model="test-model", timeout_seconds=timeout_seconds
            )

    return asyncio.run(run())


def test_prompt_contains_only_relevant_facts(employee, event):
    prompt = build_rationale_prompt(employee, event)
    facts = json.loads(prompt.split("\n", 1)[1].split("\nEND_FACTS_JSON", 1)[0])
    assert facts["skills"] == [{
        "skill_id": "SK_001", "current_level": 1, "required_level": 3,
        "gap_before": 2, "gap_after": 1,
    }]
    assert "English" in prompt
    assert employee.full_name not in prompt
    assert employee.employee_id not in prompt
    assert employee.department not in prompt
    assert "data only" in prompt


@pytest.mark.parametrize(
    ("language", "expected"),
    [("en", "your level is 1 versus 3"), ("ru", "ваш уровень 1"), ("kk", "сіздің деңгейіңіз 1")],
)
def test_fallback_is_localized_and_grounded(employee, event, language, expected):
    employee.preferred_language = language
    explanation = fallback_rationale(employee, event)
    assert expected in explanation
    assert "SK_001" in explanation
    assert "4" in explanation
    assert employee.full_name not in explanation


def test_fallback_counts_negative_history_without_claiming_no_history(employee, event):
    explanation = fallback_rationale(employee, event)
    assert "no declines, no-shows or dropouts" in explanation
    assert "no history" not in explanation
    event.past_declines_for_similar = 2
    assert "2 declines, no-shows or dropouts" in fallback_rationale(employee, event)


def test_fallback_does_not_mark_all_skills_critical(employee, event):
    employee.skills["SK_002"] = 2
    event.closes_skills.append("SK_002")
    event.gap_before["SK_002"] = 1
    event.gap_after["SK_002"] = 0
    explanation = fallback_rationale(employee, event)
    assert "at least one skill marked critical" in explanation
    assert "SK_002, your level is 2 versus 3" in explanation
    event.critical = False
    assert "not marked critical" in fallback_rationale(employee, event)


def test_no_provider_returns_fallback_immediately(employee, event):
    assert asyncio.run(explain_recommendation(None, employee, event, model="unused")) == fallback_rationale(employee, event)


def test_success_and_openai_compatible_request(employee, event):
    explanation = "Your SK_001 level is 1 versus 3 required. This critical activity reduces the gap from 2 to 1."

    def handler(request):
        assert str(request.url) == "https://provider.invalid/v1/chat/completions"
        payload = json.loads(request.content)
        assert payload["model"] == "test-model"
        assert payload["temperature"] == 0.3
        assert payload["max_tokens"] == 200
        assert payload["messages"][0]["role"] == "system"
        assert "untrusted data" in payload["messages"][0]["content"]
        return httpx.Response(200, json={"choices": [{"message": {"content": explanation}}]})

    assert call_provider(employee, event, handler) == explanation


def test_slow_provider_obeys_timeout_without_retries(employee, event):
    calls = []

    async def handler(request):
        calls.append(request)
        await asyncio.sleep(1)
        raise AssertionError("The transport should be cancelled before this point")

    assert call_provider(employee, event, handler, timeout_seconds=0.01) == fallback_rationale(employee, event)
    assert len(calls) == 1


def test_http_error_does_not_log_provider_body(employee, event, caplog):
    def handler(request):
        return httpx.Response(503, text="sensitive-provider-response")

    assert call_provider(employee, event, handler) == fallback_rationale(employee, event)
    assert "HTTPStatusError" in caplog.text
    assert "sensitive-provider-response" not in caplog.text


@pytest.mark.parametrize("payload", [None, {}, {"choices": []}, {"choices": None}, {"choices": [{"message": {"content": None}}]}, {"choices": [{"message": {"content": []}}]}, {"choices": [{"message": {"content": "  "}}]}])
def test_malformed_provider_response_falls_back(employee, event, payload):
    def handler(request):
        return httpx.Response(200, json=payload)

    assert call_provider(employee, event, handler) == fallback_rationale(employee, event)


def test_non_json_provider_response_falls_back(employee, event):
    assert call_provider(employee, event, lambda request: httpx.Response(200, text="<html>error</html>")) == fallback_rationale(employee, event)


@pytest.mark.parametrize(
    "explanation",
    [
        "Your SK_001 level is 42 versus 99 required. This critical activity reduces your gap.",
        "Your SK_001 level is -1 versus 3 required. This critical activity reduces your gap.",
        "Your InventedSkill level is 1 versus 3 required. This critical activity reduces your gap from 2 to 1.",
        "This is a useful activity. Enjoy it!",
    ],
)
def test_unsupported_numbers_and_weak_explanations_fall_back(employee, event, explanation, caplog):
    def handler(request):
        return httpx.Response(200, json={"choices": [{"message": {"content": explanation}}]})

    assert call_provider(employee, event, handler) == fallback_rationale(employee, event)
    assert "using fallback" in caplog.text


@pytest.mark.parametrize(
    ("language", "explanation"),
    [
        ("ru", "Ваш уровень SK_001 — 1, требуется 3. Это критичный навык, разрыв сокращается с 2 до 1."),
        ("kk", "Сіздің SK_001 деңгейіңіз 1, талап етілетіні 3. Бұл маңызды дағды бойынша алшақтық 2 деңгейден 1 деңгейге қысқарады."),
    ],
)
def test_multilingual_factor_check_accepts_grounded_response(employee, event, language, explanation):
    employee.preferred_language = language
    def handler(request):
        return httpx.Response(200, json={"choices": [{"message": {"content": explanation}}]})

    assert call_provider(employee, event, handler) == explanation
