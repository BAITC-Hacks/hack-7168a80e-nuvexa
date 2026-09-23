"""Check the stated computation budget at the expected dataset size."""

from pathlib import Path
from time import perf_counter

from backend.data_store import DataStore
from backend.recommendation_engine import recommend_next_steps


def test_recommendations_under_one_second_at_expected_scale():
    store = DataStore(Path(__file__).resolve().parents[1] / "sample_data")
    base_employee = store.get_employee("EMP_001").model_dump()
    extra_employees = [
        {**base_employee, "employee_id": f"BENCH_{index:03d}"}
        for index in range(194)
    ]
    store.import_employees(extra_employees)
    employee_ids = list(store.employees)
    base_history = store.get_employee_history("EMP_001")
    extra_history = [
        {
            **base_history[index % len(base_history)].model_dump(),
            "record_id": f"BENCH_REC_{index:05d}",
            "employee_id": employee_ids[index % len(employee_ids)],
        }
        for index in range(2700 - len(store.activity_history))
    ]
    store.import_history(extra_history)
    assert len(store.employees) == 200
    assert len(store.activity_history) == 2700

    # Startup/import work is outside the pure recommendation computation budget.
    timings = []
    total_start = perf_counter()
    for employee_id in employee_ids:
        start = perf_counter()
        recommend_next_steps(store, employee_id)
        timings.append(perf_counter() - start)
    elapsed = perf_counter() - total_start
    print(f"200 employees / 2700 records: max={max(timings):.4f}s, all={elapsed:.4f}s")
    assert max(timings) < 1.0
