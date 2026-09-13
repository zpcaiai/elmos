"""Implementation of B02: Fast smoke test gate selector and evaluator."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from .contracts import GateDecision


class SmokeGateEvaluator:
    """Evaluates critical path smoke tests; halts regression on failure."""

    @classmethod
    def evaluate(cls, smoke_results: Sequence[Mapping[str, Any]]) -> tuple[GateDecision, list[str]]:
        reasons: list[str] = []

        if not smoke_results:
            return GateDecision.FAIL, ["SMOKE_RESULTS_EMPTY"]

        failed_cases: list[str] = []
        for r in smoke_results:
            case_id = r.get("case_id", "unknown")
            status = r.get("status")
            if status != "PASSED":
                failed_cases.append(f"{case_id}:{status}")

        if failed_cases:
            reasons.append(f"SMOKE_TESTS_FAILED: {', '.join(failed_cases)}")
            reasons.append("REGRESSION_EXECUTION_HALTED")
            return GateDecision.FAIL, reasons

        return GateDecision.PASS, ["ALL_SMOKE_TESTS_PASSED"]
