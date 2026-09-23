"""Data integrity checks for bulk imports, CSV boundaries and completion races."""

import shutil
from concurrent.futures import ThreadPoolExecutor
from io import StringIO
from pathlib import Path
from threading import Barrier

import pandas as pd
import pytest

from backend.data_store import (
    HISTORY_COLUMNS,
    AlreadyCompletedError,
    DataStore,
    parse_history_csv,
)

SAMPLE_DATA = Path(__file__).resolve().parents[1] / "sample_data"


@pytest.fixture
def store():
    return DataStore(SAMPLE_DATA)


def new_employee(store, identifier="EMP_IMPORTED"):
    employee = store.get_employee("EMP_002").model_dump()
    employee["employee_id"] = identifier
    return employee


def new_record(identifier="REC_IMPORTED", **overrides):
    return {
        "record_id": identifier,
        "employee_id": "EMP_002",
        "event_id": "EV_004",
        "date": "2026-10-01",
        "due_date": None,
        "status": "completed",
        "completion_pct": 100,
        "score": None,
        "feedback_rating": None,
        "assigned_by": "self",
    } | overrides


def snapshot(store):
    return {
        "employees": {key: value.model_dump() for key, value in store.employees.items()},
        "history": {
            key: [record.model_dump() for record in store.get_employee_history(key)]
            for key in store.employees
        },
        "frame": store.activity_history.copy(deep=True),
    }


def assert_unchanged(store, before):
    after = snapshot(store)
    assert after["employees"] == before["employees"]
    assert after["history"] == before["history"]
    pd.testing.assert_frame_equal(after["frame"], before["frame"])


@pytest.mark.parametrize(
    "bad_record",
    [
        new_record(employee_id="UNKNOWN"),
        new_record(event_id="UNKNOWN"),
        new_record(completion_pct=101),
        new_record(status="invalid"),
    ],
)
def test_invalid_history_rolls_back_entire_import_including_valid_employee(store, bad_record):
    before = snapshot(store)
    with pytest.raises(ValueError):
        store.import_data([new_employee(store)], [bad_record])
    assert_unchanged(store, before)


def test_duplicate_ids_within_batch_are_rejected_without_partial_merge(store):
    before = snapshot(store)
    person = new_employee(store)
    with pytest.raises(ValueError, match="Duplicate employee_id"):
        store.import_employees([person, person])
    assert_unchanged(store, before)
    with pytest.raises(ValueError, match="Duplicate record_id"):
        store.import_history([new_record(), new_record()])
    assert_unchanged(store, before)


def test_one_batch_can_add_employee_and_their_referencing_history(store):
    imported = new_employee(store)
    counts = store.import_data(
        [imported], [new_record(employee_id=imported["employee_id"])]
    )
    assert counts == {"employees_imported": 1, "history_imported": 1}
    assert len(store.get_employee_history(imported["employee_id"])) == 1
    assert store.get_employee(imported["employee_id"]).skills == imported["skills"]


def test_upsert_moves_record_between_employee_indexes_without_duplication(store):
    original_count = len(store.activity_history)
    store.import_history([new_record(employee_id="EMP_002")])
    store.import_history([new_record(employee_id="EMP_003")])
    assert len(store.activity_history) == original_count + 1
    assert not any(record.record_id == "REC_IMPORTED" for record in store.get_employee_history("EMP_002"))
    assert sum(record.record_id == "REC_IMPORTED" for record in store.get_employee_history("EMP_003")) == 1


def test_concurrent_duplicate_completion_applies_skills_and_history_once(store):
    before_skill = store.get_employee("EMP_002").skills["SK_PYTHON"]
    before_count = len(store.activity_history)
    barrier = Barrier(8)

    def complete_once(_):
        barrier.wait(timeout=5)
        try:
            store.complete_activity("EMP_002", "EV_002")
            return "completed"
        except AlreadyCompletedError:
            return "conflict"

    with ThreadPoolExecutor(max_workers=8) as executor:
        results = list(executor.map(complete_once, range(8)))
    assert results.count("completed") == 1
    assert results.count("conflict") == 7
    assert len(store.activity_history) == before_count + 1
    assert store.get_employee("EMP_002").skills["SK_PYTHON"] == before_skill + 1


def test_new_record_ids_follow_imported_suffixes_without_overwriting_existing_history(store):
    store.import_history([new_record("REC_000100"), new_record("HISTORY_123")])
    before_ids = set(store.activity_history["record_id"])
    store.complete_activity("EMP_002", "EV_002")
    after_ids = set(store.activity_history["record_id"])
    assert before_ids < after_ids
    assert after_ids - before_ids == {"REC_000124"}


def test_large_numeric_record_id_is_opaque_and_does_not_break_future_completion(store):
    before_count = len(store.activity_history)
    record = new_record("REC_" + "9" * 5000, employee_id="EMP_IMPORTED")
    store.import_data([new_employee(store)], [record])
    assert store.get_employee("EMP_IMPORTED") is not None
    assert store.get_employee_history("EMP_IMPORTED")[0].record_id == record["record_id"]
    assert len(store.activity_history) == before_count + 1
    store.complete_activity("EMP_IMPORTED", "EV_002")
    assert len(store.activity_history) == before_count + 2
    assert len({item.record_id for item in store.get_employee_history("EMP_IMPORTED")}) == 2


def test_missing_role_profile_does_not_change_grade_order(store):
    assert store.get_next_grade("Uncatalogued Role", "Junior") == "Middle"
    assert store.get_next_grade("Uncatalogued Role", "Middle") == "Senior"
    assert store.get_next_grade("Uncatalogued Role", "Senior") == "Lead"
    assert store.get_next_grade("Uncatalogued Role", "Lead") is None
    assert store.get_role_profile("Uncatalogued Role", "Middle") is None


def test_empty_history_has_columns_and_supports_first_completion(tmp_path):
    shutil.copytree(SAMPLE_DATA, tmp_path, dirs_exist_ok=True)
    (tmp_path / "activity_history.csv").write_text(
        ",".join(HISTORY_COLUMNS) + "\n", encoding="utf-8"
    )
    empty_store = DataStore(tmp_path)
    assert empty_store.activity_history.empty
    assert list(empty_store.activity_history.columns) == list(HISTORY_COLUMNS)
    assert empty_store.get_employee_history("EMP_002") == []
    empty_store.complete_activity("EMP_002", "EV_002")
    assert empty_store.get_employee_history("EMP_002")[0].record_id == "REC_000001"


def test_csv_preserves_identifiers_and_reads_nullable_fields():
    content = ",".join(HISTORY_COLUMNS) + "\n0001,EMP_002,EV_004,2026-10-01,,completed,100,,,self\n"
    parsed = parse_history_csv(StringIO(content))
    assert parsed[0]["record_id"] == "0001"
    assert parsed[0]["due_date"] is parsed[0]["score"] is parsed[0]["feedback_rating"] is None


def test_fractional_completion_percentage_is_valid_in_csv_and_json(store):
    content = ",".join(HISTORY_COLUMNS) + "\nREC_PARTIAL,EMP_002,EV_002,2026-10-01,,in_progress,33.3,,,self\n"
    records = parse_history_csv(StringIO(content))
    assert records[0]["completion_pct"] == 33.3
    store.import_history(records)
    imported = next(record for record in store.get_employee_history("EMP_002") if record.record_id == "REC_PARTIAL")
    assert imported.completion_pct == 33.3


def test_malformed_csv_extra_field_is_rejected_instead_of_silently_becoming_index():
    content = ",".join(HISTORY_COLUMNS) + "\nIGNORED,REC_VALID,EMP_002,EV_002,2026-10-01,,completed,100,,,self\n"
    with pytest.raises(ValueError):
        parse_history_csv(StringIO(content))


@pytest.mark.parametrize("content", ["", "record_id,employee_id\nR1,E1\n"])
def test_csv_with_missing_headers_is_rejected(content):
    with pytest.raises(ValueError):
        parse_history_csv(StringIO(content))
