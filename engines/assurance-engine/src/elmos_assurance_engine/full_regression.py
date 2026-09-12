"""Implementation of B02: Full regression suite execution and zero-test rule validation."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from .contracts import GateDecision


class RegressionRunner:
    """Evaluates full regression test results against approved obligations."""

    @classmethod
    def evaluate(
        cls,
        regression_results: Sequence[Mapping[str, Any]],
        expected_test_count: int,
    ) -> tuple[GateDecision, list[str]]:
        reasons: list[str] = []

        # ZERO-TEST RULE: 0 tests collected/executed is an instant FAILURE when tests are expected
        total_executed = len(regression_results)
        if total_executed == 0:
            return GateDecision.FAIL, ["ZERO_TESTS_COLLECTED_OR_EXECUTED"]

        if total_executed < expected_test_count:
            return GateDecision.FAIL, [
                f"TEST_COUNT_UNDER_EXPECTED: executed {total_executed} < expected {expected_test_count}"
            ]

        failed_tests: list[str] = []
        skipped_tests: list[str] = []
        passed_count = 0

        for r in regression_results:
            case_id = r.get("case_id", "unknown")
            status = r.get("status")
            if status == "PASSED":
                passed_count += 1
            elif status == "SKIPPED":
                skipped_tests.append(case_id)
            else:
                failed_tests.append(f"{case_id}:{status}")

        if failed_tests:
            reasons.append(f"REGRESSION_TESTS_FAILED: {', '.join(failed_tests)}")
            return GateDecision.FAIL, reasons

        if skipped_tests:
            reasons.append(f"CRITICAL_TESTS_SKIPPED: {', '.join(skipped_tests)}")
            return GateDecision.INCONCLUSIVE, reasons

        return GateDecision.PASS, [f"ALL_{passed_count}_REGRESSION_TESTS_PASSED"]
