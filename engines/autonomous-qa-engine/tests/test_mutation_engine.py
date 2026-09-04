"""Tests for mutation testing engine and native acceleration bridge."""

from __future__ import annotations

from elmos_autonomous_qa.mutation_engine import MutationTestingEngine, run_mutation_testing
from elmos_autonomous_qa.native_mutation_bridge import is_native_available, native_evaluate_mutants


def test_mutation_engine_native_bridge():
    assert is_native_available() is True
    code = "public int calculateDiscount(int price) { if (price > 100) return price - 20; return price; }"
    res = native_evaluate_mutants(code)
    assert res is not None
    assert res["total_mutants"] >= 2
    assert res["killed_mutants"] == res["total_mutants"]
    assert res["mutation_score"] == 1.0


def test_run_mutation_testing_end_to_end():
    res = run_mutation_testing()
    assert res["status"] == "MUTATION_TEST_PASSED"
    assert res["mutation_score"] >= 0.8
    assert res["total_mutants"] >= 2
    assert res["killed_mutants"] >= 2
    assert len(res["mutants"]) >= 2
