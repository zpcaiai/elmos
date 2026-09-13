"""Deployment and Upgrade Quality Gate Engine (Batch 38 - Skill 1346).

Enforces pre-upgrade validation, schema backward compatibility, traffic drain safety,
canary error budget, and rollback plan verification before authorizing upgrades.
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import uuid

from .types import (
    DeploymentUpgradeGateAssessment,
    DeploymentUpgradeGateCheck,
    UpgradeGateCheckType,
    UpgradeGateVerdict,
)


class DeploymentUpgradeGateEngine:
    """Authorizes deployment upgrades through rigorous quality gating."""

    def __init__(self) -> None:
        self._assessments: Dict[str, DeploymentUpgradeGateAssessment] = {}

    def initiate_upgrade_assessment(
        self, deployment_id: str, from_version: str, to_version: str
    ) -> str:
        """Initialize an upgrade gate assessment for a target deployment."""
        if not deployment_id or not from_version or not to_version:
            raise ValueError("deployment_id, from_version, and to_version are required")
        if from_version == to_version:
            raise ValueError("from_version and to_version cannot be identical")

        gate_id = f"gate-{uuid.uuid4().hex[:8]}"
        assessment = DeploymentUpgradeGateAssessment(
            gate_id=gate_id,
            deployment_id=deployment_id,
            from_version=from_version,
            to_version=to_version,
            verdict=UpgradeGateVerdict.BLOCKED,
        )
        self._assessments[gate_id] = assessment
        return gate_id

    def add_gate_check(
        self, gate_id: str, check: DeploymentUpgradeGateCheck
    ) -> DeploymentUpgradeGateAssessment:
        """Add a required validation check to an upgrade gate."""
        assessment = self._assessments.get(gate_id)
        if not assessment:
            raise ValueError(f"Assessment not found: {gate_id}")

        if not check.check_id:
            check.check_id = f"chk-{uuid.uuid4().hex[:8]}"

        assessment.checks.append(check)
        return assessment

    def record_check_result(
        self,
        gate_id: str,
        check_id: str,
        passed: bool,
        actual_metrics: Optional[Dict[str, Any]] = None,
    ) -> DeploymentUpgradeGateCheck:
        """Record the verification outcome for a specific check."""
        assessment = self._assessments.get(gate_id)
        if not assessment:
            raise ValueError(f"Assessment not found: {gate_id}")

        check = next((c for c in assessment.checks if c.check_id == check_id), None)
        if not check:
            raise ValueError(f"Check not found: {check_id}")

        check.passed = passed
        check.evaluated_at = datetime.now(timezone.utc).isoformat()
        if actual_metrics:
            check.actual_metrics = actual_metrics
        return check

    def evaluate_gate(
        self, gate_id: str, operator: str = "system"
    ) -> DeploymentUpgradeGateAssessment:
        """Evaluate all gate checks and establish final upgrade authorization."""
        assessment = self._assessments.get(gate_id)
        if not assessment:
            raise ValueError(f"Assessment not found: {gate_id}")

        assessment.evaluated_at = datetime.now(timezone.utc).isoformat()
        assessment.operator = operator

        if not assessment.checks:
            assessment.verdict = UpgradeGateVerdict.BLOCKED
            return assessment

        blocking_failed = any(c.is_blocking and not c.passed for c in assessment.checks)
        if blocking_failed:
            assessment.verdict = UpgradeGateVerdict.BLOCKED
        else:
            assessment.verdict = UpgradeGateVerdict.APPROVED

        return assessment

    def override_gate(
        self, gate_id: str, operator: str, override_reason: str
    ) -> DeploymentUpgradeGateAssessment:
        """Manually override a blocked gate with audit justification."""
        assessment = self._assessments.get(gate_id)
        if not assessment:
            raise ValueError(f"Assessment not found: {gate_id}")
        if not operator or not override_reason:
            raise ValueError("operator and override_reason are required for manual override")

        assessment.verdict = UpgradeGateVerdict.CONDITIONAL_OVERRIDE
        assessment.operator = operator
        assessment.override_reason = override_reason
        assessment.evaluated_at = datetime.now(timezone.utc).isoformat()
        return assessment

    def get_assessment(self, gate_id: str) -> Optional[DeploymentUpgradeGateAssessment]:
        """Retrieve an assessment by gate ID."""
        return self._assessments.get(gate_id)

    def get_failed_blocking_checks(self, gate_id: str) -> List[DeploymentUpgradeGateCheck]:
        """Return list of failed blocking checks for a gate."""
        assessment = self._assessments.get(gate_id)
        if not assessment:
            raise ValueError(f"Assessment not found: {gate_id}")
        return [c for c in assessment.checks if c.is_blocking and not c.passed]

    def get_upgrade_gate_report(self) -> Dict[str, Any]:
        """Generate aggregate upgrade gating metrics."""
        total = len(self._assessments)
        approved = sum(
            1 for a in self._assessments.values() if a.verdict == UpgradeGateVerdict.APPROVED
        )
        blocked = sum(
            1 for a in self._assessments.values() if a.verdict == UpgradeGateVerdict.BLOCKED
        )
        overridden = sum(
            1
            for a in self._assessments.values()
            if a.verdict == UpgradeGateVerdict.CONDITIONAL_OVERRIDE
        )
        rate = round(approved / total, 4) if total > 0 else 0.0

        return {
            "total_assessments": total,
            "approved_count": approved,
            "blocked_count": blocked,
            "overridden_count": overridden,
            "clean_approval_rate": rate,
        }
