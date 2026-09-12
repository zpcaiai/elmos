"""Deterministic, bounded smoke selection and non-vacuous coverage."""
from __future__ import annotations
from fractions import Fraction
from typing import Any


def select_smoke(tests: list[dict[str, Any]], critical_ids: set[str],
                 budget_ms: int) -> dict[str, Any]:
    """Greedy set cover heuristic, NOT a guarantee of globally minimum cost."""
    if not critical_ids or budget_ms <= 0:
        raise ValueError("NONEMPTY_CRITICAL_SCOPE_AND_POSITIVE_BUDGET_REQUIRED")
    ids = [t["id"] for t in tests]
    if len(ids) != len(set(ids)):
        raise ValueError("DUPLICATE_TEST_ID")
    for test in tests:
        if type(test["estimated_ms"]) is not int or test["estimated_ms"] <= 0:
            raise ValueError("INVALID_TEST_COST")
    uncovered = set(critical_ids)
    selected: list[str] = []
    spent = 0
    remaining = list(tests)
    while uncovered:
        eligible = [t for t in remaining if set(t["covers"]) & uncovered
                    and spent + t["estimated_ms"] <= budget_ms]
        if not eligible:
            break
        eligible.sort(key=lambda t: (-Fraction(len(set(t["covers"]) & uncovered),
                                               t["estimated_ms"]), t["id"]))
        best = eligible[0]
        selected.append(best["id"])
        spent += best["estimated_ms"]
        uncovered -= set(best["covers"])
        remaining.remove(best)
    return {"selected": selected, "estimated_ms": spent,
            "uncovered": sorted(uncovered),
            "status": "PLANNED" if not uncovered else "INCONCLUSIVE",
            "tests_executed": False}


def coverage(required: set[str], results: dict[str, str]) -> dict[str, Any]:
    if not required:
        return {"numerator": 0, "denominator": 0, "ratio": None,
                "status": "INCONCLUSIVE", "missing": []}
    valid = {"PASS", "FAIL", "INCONCLUSIVE", "NOT_RUN"}
    if not set(results.values()) <= valid or not set(results) <= required:
        raise ValueError("UNRECOGNIZED_COVERAGE_RESULT")
    passed = {k for k, v in results.items() if v == "PASS"}
    missing = required - passed
    return {"numerator": len(passed), "denominator": len(required),
            "ratio": len(passed) / len(required),
            "status": "SATISFIED" if not missing else "INCOMPLETE",
            "missing": sorted(missing)}
