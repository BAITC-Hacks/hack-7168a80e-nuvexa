"""Find manual test cases in the raw Career Quest assessment dataset.

Uses only the standard library and never changes the dataset. "Lowest relative
to the next grade" means the largest positive requirement-minus-assessment gap;
ties qualify. These are assessment gaps, not the API's current skills, which also
include eligible completed activities after the employee's last review.
"""

import argparse
import csv
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

DEFAULT_DATA_DIR = Path(__file__).resolve().parents[1] / "data"
GRADE_ORDER = ("Junior", "Middle", "Senior", "Lead")
NEGATIVE_STATUSES = {"declined", "no_show", "dropped"}
CATEGORY_LABELS = {
    "gap_vs_history_conflict": "Gap-vs-history conflict",
    "new_hire": "New hire",
    "near_grade_ceiling": "Near grade ceiling",
}


def _history_facts(records: list[dict[str, str]]) -> list[dict[str, str]]:
    return [
        {key: record[key] for key in ("record_id", "event_id", "date", "status")}
        for record in sorted(
            records, key=lambda record: (record["date"], record["record_id"])
        )
    ]


def scan_scenarios(
    employees: list[dict[str, Any]],
    skills_document: dict[str, Any],
    events: list[dict[str, Any]],
    history: list[dict[str, str]],
    limit: int = 3,
) -> dict[str, list[dict[str, Any]]]:
    """Return at most ``limit`` distinct employees per category, sorted by ID.

    Missing employee skills have level zero. Promotion categories use the next
    grade of the employee's current role, regardless of a separate career goal.
    Leads have no next grade, so are excluded from those two categories.
    """
    if not 1 <= limit <= 3:
        raise ValueError("limit must be between 1 and 3")
    skills = {skill["skill_id"]: skill for skill in skills_document["skills"]}
    profiles = {
        (profile["role"], profile["grade"]): profile
        for profile in skills_document["role_profiles"]
    }
    developed_skills = {
        event["event_id"]: {item["skill_id"] for item in event["develops_skills"]}
        for event in events
    }
    by_employee = defaultdict(list)
    for record in history:
        by_employee[record["employee_id"]].append(record)
    results: dict[str, list[dict[str, Any]]] = {key: [] for key in CATEGORY_LABELS}

    for employee in sorted(employees, key=lambda item: item["employee_id"]):
        employee_id = employee["employee_id"]
        records = by_employee[employee_id]
        if employee["tenure_months"] <= 3 and all(
            record["event_id"] == "EV_004" for record in records
        ):
            results["new_hire"].append({
                "employee_id": employee_id,
                "tenure_months": employee["tenure_months"],
                "history": _history_facts(records),
            })

        grade = employee["grade"]
        if grade not in GRADE_ORDER:
            raise ValueError(f"Unknown grade for {employee_id}: {grade}")
        if grade == GRADE_ORDER[-1]:
            continue
        next_grade = GRADE_ORDER[GRADE_ORDER.index(grade) + 1]
        profile = profiles[(employee["role"], next_grade)]
        gaps = [
            {
                "skill_id": skill_id,
                "current_level": employee["skills"].get(skill_id, 0),
                "required_level": required,
                "gap": max(0, required - employee["skills"].get(skill_id, 0)),
            }
            for skill_id, required in sorted(profile["required_skills"].items())
        ]
        remaining = [gap for gap in gaps if gap["gap"] > 0]
        context = {
            "employee_id": employee_id,
            "role": employee["role"],
            "grade": grade,
            "next_grade": next_grade,
        }
        total_gap = sum(gap["gap"] for gap in remaining)
        if total_gap <= 2:
            results["near_grade_ceiling"].append(context | {
                "total_gap": total_gap,
                "remaining_gaps": remaining,
            })

        largest_gap = max((gap["gap"] for gap in remaining), default=0)
        soft_candidates = [
            gap for gap in remaining
            if gap["gap"] == largest_gap and skills[gap["skill_id"]]["type"] == "soft"
        ]
        hard_candidates = sorted(
            (
                gap for gap in remaining
                if gap["gap"] < largest_gap
                and skills[gap["skill_id"]]["type"] == "hard"
                and gap["skill_id"] in profile["critical_skills"]
            ),
            key=lambda gap: (-gap["gap"], gap["skill_id"]),
        )
        if not hard_candidates:
            continue
        for soft_gap in soft_candidates:
            relevant_history = [
                record for record in records
                if record["status"] in NEGATIVE_STATUSES
                and soft_gap["skill_id"] in developed_skills[record["event_id"]]
            ]
            if len(relevant_history) >= 2:
                results["gap_vs_history_conflict"].append(context | {
                    "soft_skill": soft_gap,
                    "hard_critical_skill": hard_candidates[0],
                    "history_count": len(relevant_history),
                    "history": _history_facts(relevant_history),
                })
                break

    return {category: matches[:limit] for category, matches in results.items()}


def find_scenarios(
    data_dir: str | Path = DEFAULT_DATA_DIR, limit: int = 3
) -> dict[str, list[dict[str, Any]]]:
    """Load the four source files and return reproducible raw-assessment cases."""
    data_dir = Path(data_dir)

    def read_json(filename: str) -> dict[str, Any]:
        with (data_dir / filename).open(encoding="utf-8-sig") as handle:
            return json.load(handle)

    employees = read_json("employees.json")["employees"]
    events = read_json("events.json")["events"]
    skills = read_json("skills.json")
    with (data_dir / "activity_history.csv").open(
        encoding="utf-8-sig", newline=""
    ) as handle:
        history = list(csv.DictReader(handle))
    return scan_scenarios(employees, skills, events, history, limit=limit)


def _format_gap(gap: dict[str, Any]) -> str:
    return (
        f"{gap['skill_id']}: {gap['current_level']} -> {gap['required_level']} "
        f"(gap {gap['gap']})"
    )


def _print_report(scenarios: dict[str, list[dict[str, Any]]], data_dir: Path) -> None:
    print(f"Dataset: {data_dir.resolve()}")
    print("Basis: raw assessment levels; the live API also applies post-review completions.")
    print("Largest positive gap defines lowest relative skill; ties qualify.")
    for category, label in CATEGORY_LABELS.items():
        matches = scenarios[category]
        print(f"\n{label} ({len(matches)} shown):")
        if not matches:
            print("  No matching employees in this dataset.")
            continue
        for match in matches:
            if category == "gap_vs_history_conflict":
                print(
                    f"  {match['employee_id']} ({match['grade']} -> {match['next_grade']}): "
                    f"soft {_format_gap(match['soft_skill'])}; "
                    f"hard/critical {_format_gap(match['hard_critical_skill'])}; "
                    f"negative history count={match['history_count']}"
                )
            elif category == "new_hire":
                print(f"  {match['employee_id']}: tenure_months={match['tenure_months']}")
            else:
                facts = "; ".join(_format_gap(gap) for gap in match["remaining_gaps"])
                print(
                    f"  {match['employee_id']} ({match['grade']} -> {match['next_grade']}): "
                    f"total_gap={match['total_gap']}; {facts or 'no remaining gaps'}"
                )
            if "history" in match:
                print("    history: " + json.dumps(match["history"], ensure_ascii=True))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--data-dir", type=Path, default=DEFAULT_DATA_DIR,
        help="Dataset folder (default: this repository's data/ from any working directory)",
    )
    parser.add_argument("--limit", type=int, choices=(1, 2, 3), default=3)
    parser.add_argument("--json", action="store_true", help="Print machine-readable results")
    args = parser.parse_args(argv)
    try:
        scenarios = find_scenarios(args.data_dir, limit=args.limit)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(f"FAIL: could not scan dataset: {exc}", file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps({
            "data_dir": str(args.data_dir.resolve()),
            "skill_basis": "raw assessment; no completed-history skill replay",
            "scenarios": scenarios,
        }, indent=2, ensure_ascii=True))
    else:
        _print_report(scenarios, args.data_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
