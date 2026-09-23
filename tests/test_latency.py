"""Endpoint-level checks that provider latency cannot serialize recommendations."""

import asyncio
import json
from contextlib import asynccontextmanager
from pathlib import Path
from time import perf_counter

import httpx

from backend.config import Settings
from backend.main import create_app
from backend.rationale_generator import fallback_rationale
from backend.recommendation_engine import recommend_next_steps

SAMPLE_DATA = Path(__file__).resolve().parents[1] / "sample_data"


@asynccontextmanager
async def mocked_api(handler, *, timeout_seconds):
    """Use real startup and routing, replacing the provider before any request."""
    app = create_app(Settings(
        data_dir=SAMPLE_DATA,
        llm_api_key="test-not-a-real-key",
        llm_base_url="https://provider.invalid/v1/",
        llm_timeout_seconds=timeout_seconds,
    ))
    async with app.router.lifespan_context(app):
        await app.state.llm_client.aclose()
        app.state.llm_client = httpx.AsyncClient(
            base_url="https://provider.invalid/v1/",
            transport=httpx.MockTransport(handler),
        )
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app), base_url="http://testserver"
        ) as api:
            yield app, api


def test_recommendation_explanations_start_concurrently():
    async def run():
        all_started = asyncio.Event()
        calls = 0
        active = 0
        peak_active = 0

        async def handler(request):
            nonlocal calls, active, peak_active
            calls += 1
            active += 1
            peak_active = max(peak_active, active)
            if calls == 3:
                all_started.set()
            try:
                # A sequential implementation cannot cross this barrier before
                # its first request times out, and will never reach peak == 3.
                await all_started.wait()
                await asyncio.sleep(0.01)
                payload = json.loads(request.content)
                prompt = payload["messages"][1]["content"]
                facts = json.loads(prompt.split("\n", 1)[1].split("\nEND_FACTS_JSON", 1)[0])
                skill = facts["skills"][0]
                critical = "critical" if facts["closes_at_least_one_critical_skill_gap"] else "not marked critical"
                content = (
                    f"Your {skill['skill_id']} level is {skill['current_level']} "
                    f"versus {skill['required_level']} required for the next grade. "
                    f"The activity addresses a skill gap that is {critical}, "
                    f"reducing it from {skill['gap_before']} to {skill['gap_after']}."
                )
                return httpx.Response(200, json={"choices": [{"message": {"content": content}}]})
            finally:
                active -= 1

        async with mocked_api(handler, timeout_seconds=0.5) as (app, api):
            assert len(recommend_next_steps(app.state.data_store, "EMP_001")) == 3
            response = await asyncio.wait_for(api.get("/employees/EMP_001/recommendations"), 3)
        assert response.status_code == 200
        assert len(response.json()["recommendations"]) == 3
        assert calls == peak_active == 3
        assert active == 0
        assert all(item["rationale"].startswith("Your ") for item in response.json()["recommendations"])

    asyncio.run(run())


def test_recommendation_endpoint_returns_fallbacks_within_shared_timeout():
    async def run():
        calls = 0
        cancelled = 0
        active = 0
        peak_active = 0

        async def handler(request):
            nonlocal calls, cancelled, active, peak_active
            calls += 1
            active += 1
            peak_active = max(peak_active, active)
            try:
                # Simulate a provider that never sends a response. No network is
                # involved; cancellation must come from the rationale deadline.
                await asyncio.Future()
                raise AssertionError("An unresponsive provider must be cancelled")
            except asyncio.CancelledError:
                cancelled += 1
                raise
            finally:
                active -= 1

        async with mocked_api(handler, timeout_seconds=0.05) as (app, api):
            store = app.state.data_store
            employee = store.get_employee("EMP_001")
            expected = {
                event.event_id: fallback_rationale(employee, event)
                for event in recommend_next_steps(store, "EMP_001")
            }
            assert len(expected) == 3
            started = perf_counter()
            response = await asyncio.wait_for(api.get("/employees/EMP_001/recommendations"), 1)
            elapsed = perf_counter() - started
        assert response.status_code == 200
        actual = {item["event_id"]: item["rationale"] for item in response.json()["recommendations"]}
        assert actual == expected
        assert calls == cancelled == peak_active == 3
        assert active == 0
        assert elapsed < 1

    asyncio.run(run())
