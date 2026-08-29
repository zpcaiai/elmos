"""ELMOS Semantic Regression Bisector Engine.

Performs O(log N) binary search across repository revisions and transformation rule
sequences to pinpoint the exact commit or AST modification that introduced a semantic flaw.
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import asdict, dataclass
from typing import Any, Callable, Dict, List, Optional


@dataclass
class BisectStep:
    step_index: int
    rev_id: str
    evaluated_verdict: str  # PASS / FAIL
    evaluated_at: float


@dataclass
class BisectResult:
    status: str
    first_bad_revision: Optional[str]
    total_steps: int
    culprit_message: str
    history_length: int
    bisect_duration_ms: float
    steps: List[BisectStep]


class SemanticRegressionBisector:
    """Automated binary search over revision history to locate regression origins."""

    def bisect_revisions(
        self,
        revisions: List[Dict[str, Any]],
        evaluator_fn: Optional[Callable[[Dict[str, Any]], bool]] = None,
    ) -> BisectResult:
        """Execute binary search over a linear list of revisions (oldest to newest)."""
        start_time = time.perf_counter()
        if not revisions:
            return BisectResult(
                status="EMPTY_HISTORY",
                first_bad_revision=None,
                total_steps=0,
                culprit_message="No revisions provided for bisect",
                history_length=0,
                bisect_duration_ms=0.0,
                steps=[],
            )

        if evaluator_fn is None:
            # Default built-in evaluator: inspects 'is_valid' flag or test presence
            evaluator_fn = lambda rev: rev.get("is_valid", True) is True

        low = 0
        high = len(revisions) - 1
        first_bad_idx: Optional[int] = None
        steps: List[BisectStep] = []
        step_counter = 1

        while low <= high:
            mid = (low + high) // 2
            current_rev = revisions[mid]
            rev_id = current_rev.get("id", f"rev-{mid}")

            is_pass = evaluator_fn(current_rev)
            verdict = "PASS" if is_pass else "FAIL"

            steps.append(
                BisectStep(
                    step_index=step_counter,
                    rev_id=rev_id,
                    evaluated_verdict=verdict,
                    evaluated_at=time.time(),
                )
            )
            step_counter += 1

            if not is_pass:
                first_bad_idx = mid
                high = mid - 1  # Look for earlier bad revisions
            else:
                low = mid + 1  # Look in newer revisions

        duration_ms = round((time.perf_counter() - start_time) * 1000, 3)

        if first_bad_idx is not None:
            culprit = revisions[first_bad_idx]
            culprit_id = culprit.get("id", f"rev-{first_bad_idx}")
            culprit_msg = culprit.get("message", "Semantic constraint violation introduced")
            return BisectResult(
                status="FOUND_CULPRIT",
                first_bad_revision=culprit_id,
                total_steps=len(steps),
                culprit_message=culprit_msg,
                history_length=len(revisions),
                bisect_duration_ms=duration_ms,
                steps=steps,
            )

        return BisectResult(
            status="ALL_PASSING",
            first_bad_revision=None,
            total_steps=len(steps),
            culprit_message="All revisions passed verification",
            history_length=len(revisions),
            bisect_duration_ms=duration_ms,
            steps=steps,
        )


# Global singleton
_regression_bisector = SemanticRegressionBisector()


def run_semantic_bisect(
    revisions: Optional[List[Dict[str, Any]]] = None,
    good_rev: Optional[str] = None,
    bad_rev: Optional[str] = None,
) -> Dict[str, Any]:
    """Top-level helper for semantic regression bisecting."""
    if revisions is None:
        # Generate representative sample historical sequence
        revisions = [
            {"id": "c101", "message": "Initial Java Spring setup", "is_valid": True},
            {"id": "c102", "message": "Add OrderController REST API", "is_valid": True},
            {"id": "c103", "message": "Introduce PaymentService decimal arithmetic", "is_valid": True},
            {"id": "c104", "message": "Refactor Collections to fast hashtables (Regression: Unsafe Mutability)", "is_valid": False},
            {"id": "c105", "message": "Add Kafka notification dispatcher", "is_valid": False},
            {"id": "c106", "message": "Bump Spring Boot version to 3.4.0", "is_valid": False},
        ]

    res = _regression_bisector.bisect_revisions(revisions)
    return {
        "status": res.status,
        "first_bad_revision": res.first_bad_revision,
        "culprit_message": res.culprit_message,
        "total_steps": res.total_steps,
        "history_length": res.history_length,
        "bisect_duration_ms": res.bisect_duration_ms,
        "steps": [asdict(s) for s in res.steps],
    }
