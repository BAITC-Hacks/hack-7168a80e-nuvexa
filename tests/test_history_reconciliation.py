"""Effective skills follow assessed profiles and corrected completion history."""

import csv
import json
import shutil
from datetime import timedelta
from pathlib import Path

import pytest

from backend.config import SNAPSHOT_DATE
from backend.data_store import HISTORY_COLUMNS, AlreadyCompletedError, DataStore

SAMPLE_DATA = Path(__file__).resolve().parents[1] / "sample_data"
REVIEW_DATE = SNAPSHOT_DATE - timedelta(days=10)
BASE_SKILLS = {
    "SK_SQL": 1,
    "SK_PYTHON": 1,
    "SK_ANALYTICS": 1,
    "SK_COMMUNICATION": 1,
    "SK_LEADERSHIP": 0,
}


@pytest.fixture
def dataset_dir(tmp_path):
    shutil.copytree(SAMPLE_DATA, tmp_path, dirs_exist_ok=True)
    employee_path = tmp_path / "employees.json"
    document = json.loads(employee_path.read_text(encoding="utf-8"))
    for employee in document["employees"]:
        if employee["employee_id"] in {"EMP_002", "EMP_005"}:
            employee["last_review_date"] = REVIEW_DATE.isoformat()
            employee["skills"] = BASE_SKILLS.copy()
    employee_path.write_text(json.dumps(document), encoding="utf-8")
    write_history(tmp_path, [])
    return tmp_path


@pytest.fixture
def store(dataset_dir):
    return DataStore(dataset_dir)


def write_history(dataset_dir, records):
    with (dataset_dir / "activity_history.csv").open(
        "w", encoding="utf-8", newline=""
    ) as handle:
        writer = csv.DictWriter(handle, fieldnames=HISTORY_COLUMNS)
        writer.writeheader()
        writer.writerows(records)


def assessed_employee(dataset_dir, employee_id="EMP_002"):
    document = json.loads((dataset_dir / "employees.json").read_text(encoding="utf-8"))
    return next(
        employee for employee in document["employees"]
        if employee["employee_id"] == employee_id
    )


def completion(record_id="REC_REPLAY", **overrides):
    return {
        "record_id": record_id,
        "employee_id": "EMP_002",
        "event_id": "EV_001",
        "date": SNAPSHOT_DATE.isoformat(),
        "due_date": None,
        "status": "completed",
        "completion_pct": 100,
        "score": None,
        "feedback_rating": None,
        "assigned_by": "self",
    } | overrides


def test_startup_applies_post_review_completions_through_snapshot(dataset_dir):
    write_history(dataset_dir, [
        completion(),
        completion(
            "REC_PYTHON", event_id="EV_002",
            date=(REVIEW_DATE + timedelta(days=1)).isoformat(),
        ),
    ])

    loaded = DataStore(dataset_dir)

    assert loaded.get_employee("EMP_002").skills == BASE_SKILLS | {
        "SK_SQL": 2, "SK_PYTHON": 2,
    }
    assert len(loaded.get_employee_history("EMP_002")) == 2
    assert assessed_employee(dataset_dir)["skills"] == BASE_SKILLS


def test_ineligible_history_is_retained_without_changing_assessed_skills(store, dataset_dir):
    unreviewed = assessed_employee(dataset_dir, "EMP_005")
    unreviewed["last_review_date"] = None
    records = [
        completion("REC_BEFORE", date=(REVIEW_DATE - timedelta(days=1)).isoformat()),
        completion("REC_ON_REVIEW", date=REVIEW_DATE.isoformat()),
        completion("REC_FUTURE", date=(SNAPSHOT_DATE + timedelta(days=1)).isoformat()),
        completion("REC_UNREVIEWED", employee_id="EMP_005"),
    ] + [
        completion(f"REC_{status.upper()}", status=status, completion_pct=50)
        for status in ("in_progress", "dropped", "no_show", "declined", "overdue")
    ]

    store.import_data([unreviewed], records)

    assert store.get_employee("EMP_002").skills == BASE_SKILLS
    assert store.get_employee("EMP_005").skills == BASE_SKILLS
    assert len(store.activity_history) == len(records)


def test_reimporting_history_and_unrelated_profiles_does_not_repeat_gains(store, dataset_dir):
    record = completion()
    store.import_history([record])

    for _ in range(2):
        assert store.import_history([record]) == 1
        store.import_data([], [])
        store.import_employees([assessed_employee(dataset_dir, "EMP_005")])

    assert store.get_employee("EMP_002").skills == BASE_SKILLS | {"SK_SQL": 2}
    assert len(store.get_employee_history("EMP_002")) == 1


def test_status_and_date_corrections_remove_old_gains_and_can_restore_them(store):
    original = completion()
    store.import_history([original])
    assert store.get_employee("EMP_002").skills["SK_SQL"] == 2

    for correction in (
        {"status": "dropped", "completion_pct": 50},
        {"date": REVIEW_DATE.isoformat()},
        {"date": (SNAPSHOT_DATE + timedelta(days=1)).isoformat()},
    ):
        store.import_history([original | correction])
        assert store.get_employee("EMP_002").skills == BASE_SKILLS
        store.import_history([original])
        assert store.get_employee("EMP_002").skills["SK_SQL"] == 2
        assert len(store.get_employee_history("EMP_002")) == 1


def test_correcting_event_replaces_its_skill_effect(store):
    store.import_history([completion()])

    store.import_history([completion(event_id="EV_002")])

    assert store.get_employee("EMP_002").skills == BASE_SKILLS | {"SK_PYTHON": 2}
    history = store.get_employee_history("EMP_002")
    assert len(history) == 1
    assert history[0].event_id == "EV_002"


def test_correcting_employee_moves_skill_effect_to_the_new_employee(store):
    store.import_history([completion()])

    store.import_history([completion(employee_id="EMP_005")])

    assert store.get_employee("EMP_002").skills == BASE_SKILLS
    assert store.get_employee("EMP_005").skills == BASE_SKILLS | {"SK_SQL": 2}
    assert store.get_employee_history("EMP_002") == []
    assert len(store.get_employee_history("EMP_005")) == 1


def test_assessment_replacement_replays_only_history_after_its_review(store, dataset_dir):
    store.import_history([completion()])
    assessment = assessed_employee(dataset_dir)
    assessment["skills"]["SK_SQL"] = 3

    store.import_employees([assessment])
    assert store.get_employee("EMP_002").skills["SK_SQL"] == 4
    store.import_employees([assessment])
    assert store.get_employee("EMP_002").skills["SK_SQL"] == 4

    assessment["last_review_date"] = SNAPSHOT_DATE.isoformat()
    store.import_employees([assessment])
    assert store.get_employee("EMP_002").skills["SK_SQL"] == 3
    assert len(store.get_employee_history("EMP_002")) == 1


def test_history_caps_gains_preserves_advanced_skills_and_adds_missing_skills(store, dataset_dir):
    assessment = assessed_employee(dataset_dir)
    assessment["skills"].update(SK_SQL=4, SK_COMMUNICATION=3)
    assessment["skills"].pop("SK_LEADERSHIP")

    store.import_data([assessment], [
        completion("REC_LOWER_CAP", event_id="EV_006"),
        completion("REC_CAPPED", event_id="EV_003"),
        completion("REC_NEW_SKILL", event_id="EV_011"),
    ])

    assert store.get_employee("EMP_002").skills == BASE_SKILLS | {
        "SK_SQL": 4, "SK_COMMUNICATION": 4, "SK_LEADERSHIP": 1,
    }


def test_chronological_replay_respects_course_caps_after_date_corrections(store):
    advanced = completion("REC_A_ADVANCED", date=(SNAPSHOT_DATE - timedelta(days=1)).isoformat())
    foundation = completion(
        "REC_Z_FOUNDATION", event_id="EV_006",
        date=(SNAPSHOT_DATE - timedelta(days=2)).isoformat(),
    )
    # Import order and record ID order both put the later activity first.
    store.import_history([advanced, foundation])
    assert store.get_employee("EMP_002").skills["SK_SQL"] == 3

    store.import_history([foundation | {"date": SNAPSHOT_DATE.isoformat()}])
    assert store.get_employee("EMP_002").skills["SK_SQL"] == 2


@pytest.mark.parametrize("last_review_date", [None, SNAPSHOT_DATE.isoformat()])
def test_live_completion_applies_once_and_survives_later_imports(
    store, dataset_dir, last_review_date,
):
    assessment = assessed_employee(dataset_dir)
    assessment["last_review_date"] = last_review_date
    store.import_employees([assessment])

    completed = store.complete_activity("EMP_002", "EV_001")
    assert completed.skills == BASE_SKILLS | {"SK_SQL": 2}
    with pytest.raises(AlreadyCompletedError):
        store.complete_activity("EMP_002", "EV_001")

    own_record = store.get_employee_history("EMP_002")[0].model_dump()
    store.import_data(
        [assessed_employee(dataset_dir, "EMP_005")],
        [completion("REC_OTHER", employee_id="EMP_005", event_id="EV_002")],
    )
    store.import_history([own_record])

    assert store.get_employee("EMP_002").skills == BASE_SKILLS | {"SK_SQL": 2}
    assert len(store.get_employee_history("EMP_002")) == 1
    assert store.get_employee("EMP_005").skills == BASE_SKILLS | {"SK_PYTHON": 2}


def test_live_completion_follows_existing_same_day_history_despite_record_id_order(store):
    store.import_history([completion("REC_ZZZ")])
    assert store.get_employee("EMP_002").skills["SK_SQL"] == 2

    # The newly generated REC_000001 sorts before REC_ZZZ lexically, but the
    # already learned SQL must remain at this refresher's level-two cap.
    completed = store.complete_activity("EMP_002", "EV_006")
    assert completed.skills["SK_SQL"] == 2

    store.import_history([
        completion("REC_UNRELATED", employee_id="EMP_005", event_id="EV_002"),
    ])
    assert store.get_employee("EMP_002").skills["SK_SQL"] == 2
    assert len(store.get_employee_history("EMP_002")) == 2


def test_same_day_live_completions_keep_execution_order_when_id_width_changes(store, dataset_dir):
    assessment = assessed_employee(dataset_dir)
    assessment["skills"]["SK_COMMUNICATION"] = 3
    store.import_data([assessment], [
        completion("REC_999998", employee_id="EMP_005", event_id="EV_004"),
    ])

    # REC_999999 teaches up to four; the subsequent REC_1000000 can teach five.
    assert store.complete_activity("EMP_002", "EV_003").skills["SK_COMMUNICATION"] == 4
    assert store.complete_activity("EMP_002", "EV_036").skills["SK_COMMUNICATION"] == 5

    store.import_history([
        completion("REC_UNRELATED", employee_id="EMP_005", event_id="EV_002"),
    ])
    assert store.get_employee("EMP_002").skills["SK_COMMUNICATION"] == 5
