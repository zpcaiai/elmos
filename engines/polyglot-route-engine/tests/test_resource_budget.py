from __future__ import annotations

import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor

import pytest

from elmos_polyglot_route import resource_budget, toolchains
from elmos_polyglot_route.resource_budget import ExecutionBudget, bounded_map, keyed_lock
from elmos_polyglot_route.toolchains import ExactToolchain


def test_memory_budget_limits_running_and_submitted_work() -> None:
    budget = ExecutionBudget(max_workers=8, memory_budget_mib=1024, per_worker_mib=512)
    active = 0
    peak = 0
    consumed = 0
    guard = threading.Lock()
    def inputs():
        nonlocal consumed
        for value in range(12):
            consumed += 1
            yield value
    def work(value):
        nonlocal active, peak
        with guard:
            active += 1
            peak = max(peak, active)
        time.sleep(0.01)
        with guard:
            active -= 1
        return value
    results = bounded_map(work, inputs(), budget)
    assert next(results) == 0
    assert consumed == 2
    assert list(results) == list(range(1, 12))
    assert peak == 2


def test_worker_failure_does_not_run_whole_unbounded_input_queue() -> None:
    consumed = []
    def work(value):
        consumed.append(value)
        if value == 0:
            raise RuntimeError("fail closed")
        time.sleep(0.01)
        return value
    with pytest.raises(RuntimeError, match="fail closed"):
        list(bounded_map(work, range(1000), ExecutionBudget(max_workers=2)))
    assert set(consumed) <= {0, 1}


@pytest.mark.parametrize("values", [
    {"max_workers": 0}, {"max_workers": 100}, {"memory_budget_mib": 0},
    {"memory_budget_mib": 100}, {"max_workers": True},
])
def test_invalid_budgets_fail_before_work(values) -> None:
    with pytest.raises(ValueError, match="BUDGET_INVALID"):
        ExecutionBudget(**values)


def test_keyed_locks_retire_and_preserve_reentrancy() -> None:
    with keyed_lock("one"):
        with keyed_lock("one"):
            assert resource_budget._locks["one"][1] == 2
    assert "one" not in resource_budget._locks


def test_exact_toolchain_cold_initialization_is_singleflight(monkeypatch) -> None:
    calls = []
    def select():
        calls.append(1)
        time.sleep(0.03)
        return ExactToolchain("python", "local-test", "/fixture/python")
    monkeypatch.setattr(toolchains, "_python", select)
    toolchains.clear_exact_toolchain_cache()
    try:
        with ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(lambda _: toolchains.exact_toolchain("python"), range(8)))
        assert len(calls) == 1
        assert len(set(results)) == 1
    finally:
        toolchains.clear_exact_toolchain_cache()


def test_parallel_discovery_and_batch_keep_all_failed_units_and_order(tmp_path, monkeypatch) -> None:
    from elmos_polyglot_route import batch
    from elmos_polyglot_route.discovery import discover_repository
    from elmos_polyglot_route.models import RouteError
    from elmos_polyglot_route.repository import plan_repository
    root = tmp_path / "source"
    root.mkdir()
    cases = tmp_path / "cases"
    cases.mkdir()
    for index in range(4):
        (root / f"source{index}.py").write_text("def identity(value: int) -> int:\n    return value\n")
        (cases / f"WU-{index + 1:05d}.json").write_text('[{"args":[1],"expected":1}]')
    plan = plan_repository(root, "local:bounded-test", "python", "typescript")
    sequential = discover_repository(plan, root)
    budget = ExecutionBudget(max_workers=2)
    parallel = discover_repository(plan, root, execution_budget=budget)
    assert parallel == sequential
    active = 0
    peak = 0
    guard = threading.Lock()
    def failed_migration(*args, **kwargs):
        nonlocal active, peak
        with guard:
            active += 1
            peak = max(peak, active)
        time.sleep(0.02)
        with guard:
            active -= 1
        raise RouteError("EXACT_TOOLCHAIN_TEST_FAILURE")
    monkeypatch.setattr(batch, "migrate", failed_migration)
    output = tmp_path / "output"
    result = batch.run_batch(parallel, root, cases, output, execution_budget=budget)
    assert peak == 2
    assert result["status"] == "PARTIAL"
    assert result["status_counts"] == {"FAILED": 4}
    assert [unit["id"] for unit in result["units"]] == [f"WU-{index + 1:05d}" for index in range(4)]
    checkpoint = [json.loads(line) for line in (output / batch.CHECKPOINT_NAME).read_text().splitlines()]
    assert checkpoint == result["units"]
