"""Security Supply Chain Gate Engine (Batch 40 - Skill 1392).

Enforces comprehensive security supply chain quality gates covering SLSA provenance,
SBOM validation, secret scanning, vulnerability threshold enforcement, and signature verification.
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import uuid

from .types import (
    SupplyChainCheckType,
    SupplyChainGateAssessment,
    SupplyChainGateCheck,
    SupplyChainGateVerdict,
)


class SecuritySupplyChainGateEngine:
    """Evaluates and certifies software artifacts against secure supply chain quality gates."""

    def __init__(self) -> None:
        self._assessments: Dict[str, SupplyChainGateAssessment] = {}

    def initiate_assessment(self, release_id: str, artifact_hash: str) -> str:
        """Start a supply chain evaluation for a target release and artifact digest."""
        if not release_id or not artifact_hash:
            raise ValueError("release_id and artifact_hash are required")

        assessment_id = f"scg-{uuid.uuid4().hex[:8]}"
        assessment = SupplyChainGateAssessment(
            assessment_id=assessment_id,
            release_id=release_id,
            artifact_hash=artifact_hash,
            verdict=SupplyChainGateVerdict.REJECTED,
        )
        self._assessments[assessment_id] = assessment
        return assessment_id

    def add_check(
        self, assessment_id: str, check: SupplyChainGateCheck
    ) -> SupplyChainGateCheck:
        """Register a supply chain requirement check into an assessment."""
        assessment = self._assessments.get(assessment_id)
        if not assessment:
            raise ValueError(f"Assessment not found: {assessment_id}")

        if not check.check_id:
            check.check_id = f"chk-{uuid.uuid4().hex[:8]}"

        assessment.checks.append(check)
        return check

    def record_check_result(
        self, assessment_id: str, check_id: str, passed: bool, details: str = ""
    ) -> SupplyChainGateCheck:
        """Record the pass/fail determination and evidence details for a check."""
        assessment = self._assessments.get(assessment_id)
        if not assessment:
            raise ValueError(f"Assessment not found: {assessment_id}")

        check = next((c for c in assessment.checks if c.check_id == check_id), None)
        if not check:
            raise ValueError(f"Check not found: {check_id}")

        check.passed = passed
        check.details = details
        check.evaluated_at = datetime.now(timezone.utc).isoformat()
        return check

    def evaluate_gate(
        self, assessment_id: str, evaluator: str = "sec-gate-robot"
    ) -> SupplyChainGateAssessment:
        """Evaluate all checks and determine the gate verdict."""
        assessment = self._assessments.get(assessment_id)
        if not assessment:
            raise ValueError(f"Assessment not found: {assessment_id}")

        assessment.evaluated_by = evaluator
        assessment.evaluated_at = datetime.now(timezone.utc).isoformat()

        if not assessment.checks:
            assessment.verdict = SupplyChainGateVerdict.REJECTED
            return assessment

        blocking_failures = [c for c in assessment.checks if c.blocking and not c.passed]
        non_blocking_failures = [c for c in assessment.checks if not c.blocking and not c.passed]

        if blocking_failures:
            assessment.verdict = SupplyChainGateVerdict.REJECTED
        elif non_blocking_failures:
            assessment.verdict = SupplyChainGateVerdict.CONDITIONAL_WAIVER
            assessment.waiver_justification = (
                f"Requires remediation of {len(non_blocking_failures)} advisory check(s)"
            )
        else:
            assessment.verdict = SupplyChainGateVerdict.APPROVED

        return assessment

    def grant_emergency_waiver(
        self, assessment_id: str, justification: str, approver: str
    ) -> SupplyChainGateAssessment:
        """Grant an explicit emergency waiver for a rejected release (prohibited for critical SLSA)."""
        assessment = self._assessments.get(assessment_id)
        if not assessment:
            raise ValueError(f"Assessment not found: {assessment_id}")

        if not justification or not approver:
            raise ValueError("justification and approver are required")

        slsa_failure = any(
            c.check_type == SupplyChainCheckType.SLSA_LEVEL and not c.passed
            for c in assessment.checks
        )
        if slsa_failure:
            raise PermissionError("Cannot grant emergency waiver when SLSA level check fails")

        assessment.verdict = SupplyChainGateVerdict.CONDITIONAL_WAIVER
        assessment.waiver_justification = f"Emergency waiver granted by {approver}: {justification}"
        return assessment

    def get_assessment(self, assessment_id: str) -> Optional[SupplyChainGateAssessment]:
        """Retrieve assessment record by ID."""
        return self._assessments.get(assessment_id)

    def get_failed_blocking_checks(self, assessment_id: str) -> List[SupplyChainGateCheck]:
        """Get all blocking checks that failed for an assessment."""
        assessment = self._assessments.get(assessment_id)
        if not assessment:
            raise ValueError(f"Assessment not found: {assessment_id}")

        return [c for c in assessment.checks if c.blocking and not c.passed]

    def get_supply_chain_gate_report(self) -> Dict[str, Any]:
        """Generate aggregated gate operations and compliance summary."""
        total = len(self._assessments)
        approved = sum(
            1 for a in self._assessments.values() if a.verdict == SupplyChainGateVerdict.APPROVED
        )
        rejected = sum(
            1 for a in self._assessments.values() if a.verdict == SupplyChainGateVerdict.REJECTED
        )
        waived = sum(
            1 for a in self._assessments.values() if a.verdict == SupplyChainGateVerdict.CONDITIONAL_WAIVER
        )
        total_checks = sum(len(a.checks) for a in self._assessments.values())

        return {
            "total_assessments": total,
            "approved_count": approved,
            "rejected_count": rejected,
            "waived_count": waived,
            "pass_rate": round(approved / total, 4) if total > 0 else 0.0,
            "total_evaluated_checks": total_checks,
        }
