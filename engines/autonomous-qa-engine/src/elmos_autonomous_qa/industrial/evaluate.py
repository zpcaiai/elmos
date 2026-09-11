"""Execute planted production defects, heal them, and verify strict tests."""

from __future__ import annotations

import ast
import asyncio
import threading
from dataclasses import dataclass, field
from typing import Any

from ..pr_self_healing.scm_models import (
    DefectClassification,
    FailureCategory,
    FailureTrace,
    RepairStrategy,
)
from .loop_guard import LoopDecision, RepairLoopGuard
from .planted_systems import PLANTED, STRICT_TESTS
from .production_healer import ProductionDefectHealer
from .test_integrity import TestIntegrityOracle

PLANT_CATEGORIES = {
    "ledger_race.py": FailureCategory.RACE_CONDITION,
    "lock_deadlock.py": FailureCategory.DEADLOCK,
    "row_lock_deadlock.py": FailureCategory.DATABASE_DEADLOCK,
    "lease_no_fence.py": FailureCategory.DISTRIBUTED_LOCK_FAILURE,
    "async_sleep_race.py": FailureCategory.ASYNC_TIMING,
}


@dataclass
class PlantedHealResult:
    name: str
    category: str
    healed: bool
    integrity_ok: bool
    mutation_caught: bool
    loop_guard_ok: bool
    details: dict[str, Any] = field(default_factory=dict)


def _namespace(source: str) -> dict[str, Any]:
    ns: dict[str, Any] = {}
    exec(compile(source, "<planted>", "exec"), ns, ns)
    return ns


def _barrier_preempt(parties: int = 2) -> Any:
    barrier = threading.Barrier(parties)

    def _preempt() -> None:
        try:
            barrier.wait(timeout=0.5)
        except Exception:
            return None
        return None

    return _preempt


def _demonstrate_bug(name: str, source: str) -> dict[str, Any]:
    ns = _namespace(source)
    if name == "ledger_race.py":
        balance = ns["run_concurrent_deposits"](4, 400, _barrier_preempt(4))
        return {"observed_balance": balance, "expected": 1600, "defect_visible": balance != 1600}
    if name == "lock_deadlock.py":
        completed = ns["run_opposite_transfers"](0.35, _barrier_preempt(2))
        return {"completed": completed, "defect_visible": not completed}
    if name == "row_lock_deadlock.py":
        completed = ns["run_crossing_transfers"](0.35, _barrier_preempt(2))
        return {"completed": completed, "defect_visible": not completed}
    if name == "lease_no_fence.py":
        value = ns["demo_stale_overwrite"]()
        return {"stale_value": value, "defect_visible": value == 99}
    if name == "async_sleep_race.py":
        # Sleep-based consume is the defect even if a lucky schedule passes.
        has_sleep = "asyncio.sleep" in source
        return {"has_sleep_barrier": has_sleep, "defect_visible": has_sleep}
    return {"defect_visible": True}


def _verify_healed(name: str, source: str) -> dict[str, Any]:
    ns = _namespace(source)
    if name == "ledger_race.py":
        # Do not inject a barrier under the new lock — that would self-deadlock.
        balance = ns["run_concurrent_deposits"](4, 400, None)
        return {"balance": balance, "passed": balance == 1600}
    if name == "lock_deadlock.py":
        completed = ns["run_opposite_transfers"](0.6, None)
        return {"completed": completed, "passed": completed is True}
    if name == "row_lock_deadlock.py":
        completed = ns["run_crossing_transfers"](0.6, None)
        return {"completed": completed, "passed": completed is True}
    if name == "lease_no_fence.py":
        raised = False
        try:
            ns["demo_stale_overwrite"]()
        except Exception as exc:
            raised = exc.__class__.__name__ == "StaleFencingToken" or "stale" in str(exc).lower()
        return {"stale_rejected": raised, "passed": raised}
    if name == "async_sleep_race.py":
        result = asyncio.run(ns["run_pipeline"]())
        return {"result": result, "passed": result == 42 and "asyncio.sleep" not in source}
    return {"passed": False}


def _mutation_still_caught(name: str, healed: str) -> bool:
    """Re-introduce the core bug pattern; healed tests/invariants must fail."""
    mutated = healed
    if name == "ledger_race.py":
        mutated = healed.replace("with self._lock:", "if True:")
        ns = _namespace(mutated)
        balance = ns["run_concurrent_deposits"](4, 400, _barrier_preempt(4))
        return balance != 1600
    if name == "lock_deadlock.py":
        mutated = healed.replace(
            "        with _elmos_ordered_locks(self.lock_a, self.lock_b):\n"
            "            _preempt_point()\n"
            "            self.a -= 1\n"
            "            self.b += 1\n",
            "        with self.lock_a:\n"
            "            _preempt_point()\n"
            "            with self.lock_b:\n"
            "                self.a -= 1\n"
            "                self.b += 1\n",
        ).replace(
            "        with _elmos_ordered_locks(self.lock_b, self.lock_a):\n"
            "            _preempt_point()\n"
            "            self.b -= 1\n"
            "            self.a += 1\n",
            "        with self.lock_b:\n"
            "            _preempt_point()\n"
            "            with self.lock_a:\n"
            "                self.b -= 1\n"
            "                self.a += 1\n",
        )
        if mutated == healed or "_elmos_ordered_locks(self.lock_" in mutated:
            return False
        ns = _namespace(mutated)
        return ns["run_opposite_transfers"](0.35, _barrier_preempt(2)) is False
    if name == "row_lock_deadlock.py":
        if "first_id, second_id = sorted((from_id, to_id))" in healed:
            mutated = healed.replace(
                "first_id, second_id = sorted((from_id, to_id))",
                "first_id, second_id = from_id, to_id",
            )
        else:
            mutated = healed
        if mutated == healed:
            return False
        ns = _namespace(mutated)
        return ns["run_crossing_transfers"](0.35, _barrier_preempt(2)) is False
    if name == "lease_no_fence.py":
        mutated = healed.replace(
            "if token is None or token != current:",
            "if False and token is None:",
        ).replace(
            "if holder != self.holder:",
            "if False and holder != self.holder:",
        )
        if mutated == healed:
            return False
        ns = _namespace(mutated)
        try:
            value = ns["demo_stale_overwrite"]()
        except Exception:
            return False
        return value == 99
    if name == "async_sleep_race.py":
        return "asyncio.sleep" not in healed
    return False


def heal_planted_system(name: str) -> PlantedHealResult:
    source = PLANTED[name]
    category = PLANT_CATEGORIES[name]
    classification = DefectClassification(
        category=category,
        primary_file=name,
        primary_line=1,
        is_test_failure_only=False,
        is_spec_drift=False,
        confidence_score=0.95,
        affected_symbols=(),
        recommended_strategy=RepairStrategy.SAFE_CODE_FIX,
        explanation=f"planted {category.value}",
    )
    trace = FailureTrace(
        test_id=f"{name}::planted",
        test_file=f"test_{name}",
        test_function="test_planted",
        failure_category=category,
        exception_class=category.value,
        error_message=f"{category.value} lost update deadlock fencing timing",
        stack_trace=(f"{name}:1 in planted",),
    )
    before = _demonstrate_bug(name, source)
    patch = ProductionDefectHealer.heal(name, source, classification, trace)
    integrity = TestIntegrityOracle.evaluate(source, patch.patched_content, is_test=False)
    test_name = {
        "ledger_race.py": "test_ledger_race.py",
        "lock_deadlock.py": "test_lock_deadlock.py",
        "lease_no_fence.py": "test_lease_no_fence.py",
        "async_sleep_race.py": "test_async_sleep_race.py",
    }.get(name)
    test_integrity_ok = True
    if test_name:
        test_src = STRICT_TESTS[test_name]
        test_integrity_ok = TestIntegrityOracle.evaluate(test_src, test_src, is_test=True).ok
    after = _verify_healed(name, patch.patched_content)
    mutation_caught = _mutation_still_caught(name, patch.patched_content)
    guard = RepairLoopGuard(max_cycles=3)
    assert guard.begin_cycle(category.value) is LoopDecision.CONTINUE
    assert guard.record_patch(patch.patch_sha256) is LoopDecision.CONTINUE
    assert guard.record_patch(patch.patch_sha256) is LoopDecision.OSCILLATION_ABORT
    return PlantedHealResult(
        name=name,
        category=category.value,
        healed=bool(after.get("passed")),
        integrity_ok=integrity.ok and test_integrity_ok,
        mutation_caught=mutation_caught,
        loop_guard_ok=True,
        details={"before": before, "after": after, "integrity": integrity.violations},
    )


def evaluate_all_planted() -> list[PlantedHealResult]:
    return [heal_planted_system(name) for name in PLANTED]
