"""Semantic regression localization over explicitly evaluated revisions."""

from __future__ import annotations

import time
from dataclasses import asdict, dataclass
from typing import Any, Callable, Dict, List, Mapping, Optional, Union


ExplicitVerdict = Union[bool, str]


@dataclass
class BisectStep:
    step_index: int
    rev_id: str
    evaluated_verdict: str
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


def _normalize_verdict(value: ExplicitVerdict) -> str:
    if type(value) is bool:
        return "PASS" if value else "FAIL"
    if isinstance(value, str) and value in {"PASS", "FAIL"}:
        return value
    raise ValueError("evaluator verdict must be bool, PASS, or FAIL")


def _not_run(history_length: int, message: str) -> BisectResult:
    return BisectResult(
        status="NOT_RUN",
        first_bad_revision=None,
        total_steps=0,
        culprit_message=message,
        history_length=history_length,
        bisect_duration_ms=0.0,
        steps=[],
    )


class SemanticRegressionBisector:
    """Locate a regression from a real evaluator or explicit PASS/FAIL facts."""

    def bisect_revisions(
        self,
        revisions: List[Dict[str, Any]],
        evaluator_fn: Optional[Callable[[Dict[str, Any]], ExplicitVerdict]] = None,
    ) -> BisectResult:
        """Evaluate a linear oldest-to-newest history and locate its first FAIL.

        The full result sequence is checked for monotonicity before a culprit is
        reported. This avoids returning a false boundary when a flaky or
        non-monotonic evaluator violates binary-bisection assumptions.
        """

        if not isinstance(revisions, list):
            raise ValueError("revisions must be a list")
        if not revisions:
            return _not_run(0, "No revisions were provided")
        if len(revisions) > 1_000_000:
            raise ValueError("revision history exceeds the bounded limit")

        normalized: List[Dict[str, Any]] = []
        seen_ids: set[str] = set()
        for index, revision in enumerate(revisions):
            if not isinstance(revision, Mapping):
                raise ValueError(f"revisions[{index}] must be an object")
            rev_id = revision.get("id")
            if (
                not isinstance(rev_id, str)
                or not rev_id
                or len(rev_id.encode("utf-8")) > 200
            ):
                raise ValueError(f"revisions[{index}].id is invalid")
            if rev_id in seen_ids:
                raise ValueError(f"duplicate revision id: {rev_id}")
            seen_ids.add(rev_id)
            normalized.append(dict(revision))

        if evaluator_fn is None and not all(
            revision.get("verdict") in {"PASS", "FAIL"}
            for revision in normalized
        ):
            return _not_run(
                len(normalized),
                "A real evaluator or an explicit PASS/FAIL verdict per revision is required",
            )

        started = time.perf_counter()
        steps: List[BisectStep] = []
        verdicts: List[str] = []
        for index, revision in enumerate(normalized):
            try:
                raw_verdict: ExplicitVerdict
                if evaluator_fn is None:
                    raw_verdict = revision["verdict"]
                else:
                    raw_verdict = evaluator_fn(revision)
                verdict = _normalize_verdict(raw_verdict)
            except Exception as exc:
                return BisectResult(
                    status="EVALUATION_FAILED",
                    first_bad_revision=None,
                    total_steps=len(steps),
                    culprit_message=(
                        f"Evaluator failed for {revision['id']}: {type(exc).__name__}"
                    ),
                    history_length=len(normalized),
                    bisect_duration_ms=round(
                        (time.perf_counter() - started) * 1000, 3
                    ),
                    steps=steps,
                )
            verdicts.append(verdict)
            steps.append(
                BisectStep(
                    step_index=index + 1,
                    rev_id=revision["id"],
                    evaluated_verdict=verdict,
                    evaluated_at=time.time(),
                )
            )

        duration_ms = round((time.perf_counter() - started) * 1000, 3)
        first_fail = next(
            (index for index, verdict in enumerate(verdicts) if verdict == "FAIL"),
            None,
        )
        if first_fail is None:
            return BisectResult(
                status="ALL_PASSING",
                first_bad_revision=None,
                total_steps=len(steps),
                culprit_message="Every supplied revision evaluated PASS",
                history_length=len(normalized),
                bisect_duration_ms=duration_ms,
                steps=steps,
            )
        if any(verdict == "PASS" for verdict in verdicts[first_fail + 1 :]):
            return BisectResult(
                status="NON_MONOTONIC_HISTORY",
                first_bad_revision=None,
                total_steps=len(steps),
                culprit_message=(
                    "PASS appears after FAIL; a unique regression boundary cannot be established"
                ),
                history_length=len(normalized),
                bisect_duration_ms=duration_ms,
                steps=steps,
            )

        culprit = normalized[first_fail]
        culprit_id = str(culprit["id"])
        supplied_message = culprit.get("message")
        culprit_message = (
            supplied_message
            if isinstance(supplied_message, str) and supplied_message
            else f"Revision {culprit_id} is the first explicit FAIL"
        )
        return BisectResult(
            status="FOUND_CULPRIT",
            first_bad_revision=culprit_id,
            total_steps=len(steps),
            culprit_message=culprit_message,
            history_length=len(normalized),
            bisect_duration_ms=duration_ms,
            steps=steps,
        )


_regression_bisector = SemanticRegressionBisector()


def run_semantic_bisect(
    revisions: Optional[List[Dict[str, Any]]] = None,
    good_rev: Optional[str] = None,
    bad_rev: Optional[str] = None,
    *,
    evaluator_fn: Optional[Callable[[Dict[str, Any]], ExplicitVerdict]] = None,
) -> Dict[str, Any]:
    """Top-level helper without generated history or implicit verdicts."""

    if revisions is None:
        result = _not_run(0, "Revision history is required")
    else:
        selected = revisions
        if (good_rev is None) != (bad_rev is None):
            result = _not_run(
                len(revisions), "good_rev and bad_rev must be supplied together"
            )
        elif good_rev is not None and bad_rev is not None:
            identifiers = [revision.get("id") for revision in revisions]
            if identifiers.count(good_rev) != 1 or identifiers.count(bad_rev) != 1:
                result = _not_run(
                    len(revisions), "good_rev and bad_rev must identify unique revisions"
                )
            else:
                good_index = identifiers.index(good_rev)
                bad_index = identifiers.index(bad_rev)
                if good_index >= bad_index:
                    result = _not_run(
                        len(revisions), "good_rev must precede bad_rev"
                    )
                else:
                    selected = revisions[good_index : bad_index + 1]
                    result = _regression_bisector.bisect_revisions(
                        selected, evaluator_fn=evaluator_fn
                    )
                    if result.status != "EVALUATION_FAILED" and result.steps and (
                        result.steps[0].evaluated_verdict != "PASS"
                        or result.steps[-1].evaluated_verdict != "FAIL"
                    ):
                        result = BisectResult(
                            status="BOUNDARY_VERDICT_MISMATCH",
                            first_bad_revision=None,
                            total_steps=result.total_steps,
                            culprit_message=(
                                "good_rev must evaluate PASS and bad_rev must evaluate FAIL"
                            ),
                            history_length=result.history_length,
                            bisect_duration_ms=result.bisect_duration_ms,
                            steps=result.steps,
                        )
        else:
            result = _regression_bisector.bisect_revisions(
                selected, evaluator_fn=evaluator_fn
            )
    return {
        "status": result.status,
        "first_bad_revision": result.first_bad_revision,
        "culprit_message": result.culprit_message,
        "total_steps": result.total_steps,
        "history_length": result.history_length,
        "bisect_duration_ms": result.bisect_duration_ms,
        "steps": [asdict(step) for step in result.steps],
    }
