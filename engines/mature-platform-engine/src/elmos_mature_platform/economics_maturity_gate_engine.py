"""Economics Maturity Gate Engine (Batch 44 - Skill 1474).

Enforces strict commercial and FinOps quality gates, verifying unit economics bounds,
minimum gross margins, billing reconciliation tolerances, and budget guardrails before release certification.
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import uuid

from .types import (
    EconomicsGateCheckType,
    EconomicsGateCriterion,
    EconomicsGateVerdict,
    EconomicsMaturityGateEvaluation,
)


class EconomicsMaturityGateEngine:
    """Rigorous gate engine assessing commercial economics maturity and fail-closed readiness."""

    def __init__(self) -> None:
        self._evaluations: Dict[str, EconomicsMaturityGateEvaluation] = {}

    def create_gate_evaluation(self, pack_key: str, scope: str) -> str:
        """Initialize a new economics maturity gate review."""
        if not pack_key or not scope:
            raise ValueError("pack_key and scope are required")

        eval_id = f"econ-gate-{uuid.uuid4().hex[:8]}"
        evaluation = EconomicsMaturityGateEvaluation(
            eval_id=eval_id,
            pack_key=pack_key,
            scope=scope,
            criteria={},
            overall_verdict=EconomicsGateVerdict.PENDING,
            evaluated_at=datetime.now(timezone.utc).isoformat(),
        )
        self._evaluations[eval_id] = evaluation
        return eval_id

    def add_criterion(
        self, eval_id: str, criterion: EconomicsGateCriterion
    ) -> EconomicsMaturityGateEvaluation:
        """Register an economic acceptance criterion for gate evaluation."""
        eval_obj = self._evaluations.get(eval_id)
        if not eval_obj:
            raise ValueError(f"Gate evaluation not found: {eval_id}")

        if not criterion.criterion_id:
            criterion.criterion_id = f"crit-{uuid.uuid4().hex[:8]}"

        eval_obj.criteria[criterion.criterion_id] = criterion
        return eval_obj

    def evaluate_criterion(
        self,
        eval_id: str,
        criterion_id: str,
        actual_metric: float,
        evidence_ref: str = "",
        notes: str = "",
    ) -> EconomicsGateCriterion:
        """Evaluate an individual criterion against target thresholds."""
        eval_obj = self._evaluations.get(eval_id)
        if not eval_obj:
            raise ValueError(f"Gate evaluation not found: {eval_id}")

        crit = eval_obj.criteria.get(criterion_id)
        if not crit:
            raise ValueError(f"Criterion not found: {criterion_id}")

        crit.actual_metric = actual_metric
        crit.evidence_ref = evidence_ref
        crit.notes = notes

        # Evaluate based on check type:
        # For margin, coverage, showback: higher or equal is better
        # For cost bound, tolerance, overrun: lower or equal is better
        if crit.check_type in (
            EconomicsGateCheckType.MINIMUM_GROSS_MARGIN,
            EconomicsGateCheckType.COST_ATTRIBUTION_COVERAGE,
            EconomicsGateCheckType.SHOWBACK_COMPLETENESS,
        ):
            if actual_metric >= crit.target_threshold:
                crit.verdict = EconomicsGateVerdict.PASS
            elif actual_metric >= crit.target_threshold * 0.9:
                crit.verdict = EconomicsGateVerdict.CONDITIONAL
            else:
                crit.verdict = EconomicsGateVerdict.FAIL
        else:
            # lower or equal is better
            if actual_metric <= crit.target_threshold:
                crit.verdict = EconomicsGateVerdict.PASS
            elif actual_metric <= crit.target_threshold * 1.1:
                crit.verdict = EconomicsGateVerdict.CONDITIONAL
            else:
                crit.verdict = EconomicsGateVerdict.FAIL

        return crit

    def finalize_gate(
        self, eval_id: str, evaluated_by: str = "system", sign_off_notes: str = ""
    ) -> EconomicsMaturityGateEvaluation:
        """Compute overall verdict and seal economics gate evaluation."""
        eval_obj = self._evaluations.get(eval_id)
        if not eval_obj:
            raise ValueError(f"Gate evaluation not found: {eval_id}")

        if not eval_obj.criteria:
            raise ValueError("Cannot finalize gate with zero criteria defined")

        verdicts = [c.verdict for c in eval_obj.criteria.values()]

        if any(v == EconomicsGateVerdict.FAIL for v in verdicts):
            overall = EconomicsGateVerdict.FAIL
        elif any(v == EconomicsGateVerdict.PENDING for v in verdicts):
            overall = EconomicsGateVerdict.PENDING
        elif any(v == EconomicsGateVerdict.CONDITIONAL for v in verdicts):
            overall = EconomicsGateVerdict.CONDITIONAL
        else:
            overall = EconomicsGateVerdict.PASS

        eval_obj.overall_verdict = overall
        eval_obj.evaluated_by = evaluated_by
        eval_obj.sign_off_notes = sign_off_notes
        eval_obj.evaluated_at = datetime.now(timezone.utc).isoformat()
        return eval_obj

    def get_gate_evaluation(self, eval_id: str) -> Optional[EconomicsMaturityGateEvaluation]:
        """Retrieve evaluation details."""
        return self._evaluations.get(eval_id)

    def get_economics_gate_report(self) -> Dict[str, Any]:
        """Generate platform economics gate conformance summary."""
        total = len(self._evaluations)
        by_verdict: Dict[str, int] = {v.value: 0 for v in EconomicsGateVerdict}
        for e in self._evaluations.values():
            by_verdict[e.overall_verdict.value] += 1

        return {
            "total_gate_reviews": total,
            "passed_gates": by_verdict[EconomicsGateVerdict.PASS.value],
            "failed_gates": by_verdict[EconomicsGateVerdict.FAIL.value],
            "conditional_gates": by_verdict[EconomicsGateVerdict.CONDITIONAL.value],
            "pending_gates": by_verdict[EconomicsGateVerdict.PENDING.value],
        }
