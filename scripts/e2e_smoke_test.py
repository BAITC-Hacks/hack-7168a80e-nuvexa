"""Exercise a running Career Quest API; completion mutates its in-memory history.

Run against a disposable single-worker backend. The event catalog must match the
server dataset so capped skill gains can be checked without guessing cap values.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
from pathlib import Path
from time import perf_counter
from typing import Any, Callable
from urllib.parse import quote, urlsplit

import httpx

DEFAULT_DATA_DIR = Path(__file__).resolve().parents[1] / "data"
STATUSES = ("completed", "declined", "no_show", "dropped", "in_progress", "overdue")
FACTOR_KEYWORDS = {
    "level/requirement": ("level", "required", "grade", "уров", "грейд", "требу", "деңгей", "талап"),
    "criticality": ("critical", "important", "promotion", "критич", "важн", "повышен", "маңыз", "сыни"),
    "history": (
        "history", "before", "previous", "declin", "no-show", "dropout", "participat",
        "истори", "отказ", "пропуск", "участ", "бас тарт", "қатысу", "келмеу", "тарих",
    ),
    "gap reduction": ("gap", "closes", "reduce", "разрыв", "пробел", "сокра", "алшақ", "қысқар"),
}


def require(condition: bool, message: str) -> None:
    """Fail checks even when Python runs with assertion optimization enabled."""
    if not condition:
        raise ValueError(message)


def rationale_factors(text: str) -> list[str]:
    """Count distinct en/ru/kk factor groups, not a proof of factual correctness."""
    normalized = text.casefold()
    return [name for name, words in FACTOR_KEYWORDS.items() if any(w in normalized for w in words)]


def validate_skills(value: Any) -> dict[str, int]:
    require(isinstance(value, dict), "skills must be an object")
    require(all(isinstance(k, str) and type(v) is int and 0 <= v <= 5
                for k, v in value.items()), "skill levels must be integers from 0 to 5")
    return value


def validate_recommendations(payload: Any, employee_id: str) -> list[dict]:
    require(isinstance(payload, dict), "recommendation response must be an object")
    require(payload.get("employee_id") == employee_id, "recommendation employee_id mismatch")
    rows = payload.get("recommendations")
    require(isinstance(rows, list), "recommendations must be an array")
    seen = set()
    for row in rows:
        require(isinstance(row, dict), "recommendation must be an object")
        for field in ("event_id", "title", "rationale", "format"):
            require(isinstance(row.get(field), str) and bool(row[field].strip()),
                    f"recommendation needs nonempty {field}")
        require(row["event_id"] not in seen, "duplicate recommendation event_id")
        seen.add(row["event_id"])
        require(len(row["rationale"].strip()) >= 40, f"{row['event_id']}: rationale under 40 characters")
        require(type(row.get("critical")) is bool, "critical must be a boolean")
        for field in ("score", "duration_hours"):
            number = row.get(field)
            require(type(number) in (int, float) and math.isfinite(number),
                    f"{field} must be a finite number")
        require(row["duration_hours"] > 0, "duration_hours must be positive")
        require(row["format"] in {"online", "offline", "self_paced"}, "invalid activity format")
        closes = row.get("closes_skills")
        require(isinstance(closes, list) and bool(closes)
                and all(isinstance(s, str) and s for s in closes), "closes_skills must list skill IDs")
    return rows


def validate_hr(payload: Any, kind: str) -> int:
    """Allow a valid empty aggregate on custom data, but reject malformed rows."""
    require(isinstance(payload, list), "HR response must be an array")
    for row in payload:
        require(isinstance(row, dict), "HR rows must be objects")
        strings = {"skill-gaps": ("skill_id", "skill_name"),
                   "employees-without-recommendation": ("employee_id", "full_name", "role", "grade"),
                   "participation-stats": ("event_id", "title")}[kind]
        require(all(isinstance(row.get(k), str) and row[k] for k in strings),
                "HR row has missing/invalid text fields")
        counts = {"skill-gaps": ("total_gap", "employees_affected"),
                  "employees-without-recommendation": (),
                  "participation-stats": (*STATUSES, "total")}[kind]
        require(all(type(row.get(k)) is int and row[k] >= 0 for k in counts),
                "HR counts must be nonnegative integers")
        if kind == "participation-stats":
            require(row["total"] == sum(row[s] for s in STATUSES), "participation total mismatch")
    return len(payload)


def run_smoke(
    client: httpx.Client, employee_id: str, events: dict[str, dict],
    *, emit: Callable[[str], None] = print, clock: Callable[[], float] = perf_counter,
) -> int:
    """Run independent checks despite failures; return a shell-friendly exit code."""
    failed = 0
    passed = 0
    skipped = 0
    endpoint = f"/employees/{quote(employee_id, safe='')}"

    def request(method: str, path: str) -> Any:
        response = client.request(method, path)
        require(response.status_code == 200, f"{method} {path}: HTTP {response.status_code}")
        return response.json()

    def check(label: str, action: Callable[[], Any]) -> Any:
        nonlocal failed, passed
        try:
            result = action()
        except (httpx.HTTPError, ValueError, KeyError, TypeError) as exc:
            failed += 1
            emit(f"FAIL {label}: {exc}")
            return None
        passed += 1
        emit(f"PASS {label}")
        return result

    def skip(label: str, reason: str) -> None:
        nonlocal skipped
        skipped += 1
        emit(f"SKIP {label}: {reason}")

    def profile() -> dict:
        payload = request("GET", endpoint)
        require(isinstance(payload, dict), "employee must be an object")
        require(payload.get("employee_id") == employee_id, "employee_id mismatch")
        require(all(isinstance(payload.get(k), str) and payload[k] for k in ("role", "grade")),
                "employee needs role and grade")
        validate_skills(payload.get("skills"))
        return payload

    before = check("1 employee profile", profile)

    def recommendations() -> list[dict]:
        started = clock()
        payload = request("GET", f"{endpoint}/recommendations")
        elapsed = clock() - started
        emit(f"  Recommendation response: {elapsed:.3f}s (budget < 10s)")
        require(elapsed < 10, "recommendation response exceeded the 10s budget")
        rows = validate_recommendations(payload, employee_id)
        for row in rows:
            factors = rationale_factors(row["rationale"])
            emit(f"  {row['event_id']}: {len(factors)}/4 heuristic factors ({', '.join(factors)})")
            if len(factors) < 2:
                emit(f"  WARNING {row['event_id']}: fewer than two rationale factors detected")
        if not rows:
            emit("  Empty recommendations are valid; no completion can be exercised.")
        return rows

    initial = check("2 recommendations and latency", recommendations)
    completed_id = None
    if before is not None and initial:
        event_id = initial[0]["event_id"]

        def complete() -> str:
            event = events.get(event_id)
            require(event is not None, f"{event_id} missing from local catalog; match --data-dir to server")
            developments = event["develops_skills"]
            caps = {d["skill_id"]: d["max_level"] for d in developments}
            closed = initial[0]["closes_skills"]
            require(all(s in caps for s in closed), "closed skill missing from local event catalog")
            payload = request("POST", f"{endpoint}/activities/{quote(event_id, safe='')}/complete")
            require(isinstance(payload, dict) and payload.get("event_id") == event_id,
                    "completion event_id mismatch")
            validate_recommendations(payload, employee_id)
            skills = validate_skills(payload.get("skills"))
            baseline = before["skills"]
            require(all(skills.get(s, -1) >= level for s, level in baseline.items()),
                    "completion reduced or removed an existing skill")
            expected = dict(baseline)
            for development in developments:
                skill = development["skill_id"]
                old = expected.get(skill, 0)
                expected[skill] = max(old, min(development["max_level"], old + development["gain"]))
            require(skills == expected, "returned skills do not match the catalog's capped gains")
            require(any(skills.get(s, 0) > baseline.get(s, 0)
                        or skills.get(s, 0) == baseline.get(s, 0) >= caps[s] for s in closed),
                    "no closed skill improved or was already capped")
            emit("  " + ", ".join(f"{s}: {baseline.get(s, 0)} -> {skills.get(s, 0)}" for s in closed))
            refreshed = profile()
            require(refreshed["skills"] == skills, "completion skills were not persisted in memory")
            history = refreshed.get("activity_history")
            require(isinstance(history, list) and all(isinstance(row, dict) for row in history),
                    "refreshed activity_history must be an array of objects")
            require(any(row.get("event_id") == event_id and row.get("status") == "completed"
                        for row in history),
                    "completed event missing from refreshed activity history")
            return event_id

        completed_id = check("3 complete first activity and verify skill gains", complete)
    else:
        skip("3 complete first activity", "no recommendations" if initial == [] else "earlier check failed")

    def refreshed_recommendations() -> list[dict]:
        rows = recommendations()
        if completed_id is not None:
            present = any(row["event_id"] == completed_id for row in rows)
            emit(f"  Completed {completed_id} disappeared: {'no' if present else 'yes'}")
            if completed_id == "EV_036":
                emit("  EV_036 is repeatable; either presence or absence is valid.")
            else:
                require(not present, "completed nonrecurring activity is still recommended")
        return rows

    check("4 refreshed recommendations", refreshed_recommendations)
    for kind in ("skill-gaps", "employees-without-recommendation", "participation-stats"):
        def hr_check(kind: str = kind) -> int:
            count = validate_hr(request("GET", f"/hr/{kind}"), kind)
            emit(f"  {kind}: {count} well-formed rows")
            return count
        check(f"5 /hr/{kind}", hr_check)

    emit(f"{'FAIL' if failed else 'PASS'} summary: {passed} passed, {failed} failed, {skipped} skipped")
    return int(failed > 0)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("employee_id", help="Real employee ID from find_test_scenarios.py")
    parser.add_argument("--base-url", default=os.getenv("CAREER_QUEST_TEST_API_URL") or "http://localhost:8000",
                        help="API origin (default: CAREER_QUEST_TEST_API_URL or http://localhost:8000)")
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR,
                        help="Dataset matching the server, for event skill caps (default: project data/)")
    args = parser.parse_args(argv)
    try:
        parsed = urlsplit(args.base_url)
        require(parsed.scheme in {"http", "https"} and bool(parsed.netloc), "base URL must use HTTP(S)")
        require(not parsed.username and not parsed.password and not parsed.query and not parsed.fragment,
                "base URL must not contain credentials, query or fragment")
        catalog = json.loads((args.data_dir / "events.json").read_text(encoding="utf-8-sig"))
        events = {event["event_id"]: event for event in catalog["events"]}
        print(f"Smoke test: {args.employee_id} against {args.base_url}")
        print("This completes the first recommended activity and changes server memory; restart to reset.")
        with httpx.Client(base_url=args.base_url.rstrip("/"), timeout=12, trust_env=False) as client:
            return run_smoke(client, args.employee_id, events)
    except (OSError, ValueError, KeyError, TypeError, httpx.InvalidURL) as exc:
        print(f"FAIL setup: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
