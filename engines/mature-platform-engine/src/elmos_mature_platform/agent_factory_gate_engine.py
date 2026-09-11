"""Agent Factory Gate Engine (Batch 42 - Skill 1434).

Enforces quality, safety boundaries, budget compliance, and precision gates
prior to promoting autonomous agents into production environments.
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import uuid

from .types import (
    AgentEvaluationCriterion,
    AgentFactoryGateSubmission,
    AgentFactoryGateVerdict,
    AgentGateCheckItem,
)


class AgentFactoryGateEngine:
    """Quality gatekeeper for autonomous agent releases into production."""

    def __init__(self) -> None:
        self._submissions: Dict[str, AgentFactoryGateSubmission] = {}

    def submit_agent_for_gating(
        self,
        agent_id: str,
        agent_version: str,
        role: str,
        target_env: str = "production",
    ) -> str:
        """Submit an agent for evaluation through the factory gate."""
        if not agent_id or not agent_version:
            raise ValueError("agent_id and agent_version are required")

        submission_id = f"sub-{uuid.uuid4().hex[:8]}"
        submission = AgentFactoryGateSubmission(
            submission_id=submission_id,
            agent_id=agent_id,
            agent_version=agent_version,
            agent_role=role,
            target_environment=target_env,
            verdict=AgentFactoryGateVerdict.INSUFFICIENT_EVALUATION,
        )
        self._submissions[submission_id] = submission
        return submission_id

    def add_gate_check(
        self, submission_id: str, check: AgentGateCheckItem
    ) -> AgentFactoryGateSubmission:
        """Add a required evaluation check to a submission."""
        sub = self._submissions.get(submission_id)
        if not sub:
            raise ValueError(f"Submission not found: {submission_id}")

        if not check.check_id:
            check.check_id = f"chk-{uuid.uuid4().hex[:8]}"

        sub.checks.append(check)
        return sub

    def record_check_result(
        self,
        submission_id: str,
        check_id: str,
        actual_value: float,
        passed: bool,
        notes: str = "",
    ) -> AgentGateCheckItem:
        """Record execution outcome for a specific check item."""
        sub = self._submissions.get(submission_id)
        if not sub:
            raise ValueError(f"Submission not found: {submission_id}")

        check = next((c for c in sub.checks if c.check_id == check_id), None)
        if not check:
            raise ValueError(f"Check item not found: {check_id}")

        check.actual_value = actual_value
        check.passed = passed
        check.evaluation_notes = notes
        return check

    def evaluate_gate(
        self, submission_id: str, evaluator: str = "system"
    ) -> AgentFactoryGateSubmission:
        """Compute final gate verdict and release authorization."""
        sub = self._submissions.get(submission_id)
        if not sub:
            raise ValueError(f"Submission not found: {submission_id}")

        sub.evaluated_at = datetime.now(timezone.utc).isoformat()
        sub.evaluator = evaluator

        if not sub.checks:
            sub.verdict = AgentFactoryGateVerdict.INSUFFICIENT_EVALUATION
            sub.release_permitted = False
            sub.conditions = ["No gate checks defined"]
            return sub

        critical_failed = [c for c in sub.checks if c.is_critical and not c.passed]
        non_critical_failed = [c for c in sub.checks if not c.is_critical and not c.passed]

        if critical_failed:
            sub.verdict = AgentFactoryGateVerdict.REJECTED_UNSAFE
            sub.release_permitted = False
            sub.conditions = [
                f"Critical failure: {c.criterion.value} ({c.name})" for c in critical_failed
            ]
        elif non_critical_failed:
            sub.verdict = AgentFactoryGateVerdict.CONDITIONAL_STAGING
            # Only allowed into staging if not strictly production
            sub.release_permitted = (sub.target_environment.lower() != "production")
            sub.conditions = [
                f"Requires remediation before prod: {c.name}" for c in non_critical_failed
            ]
        else:
            sub.verdict = AgentFactoryGateVerdict.READY_FOR_PRODUCTION
            sub.release_permitted = True
            sub.conditions = []

        return sub

    def override_gate_decision(
        self,
        submission_id: str,
        override_verdict: AgentFactoryGateVerdict,
        justification: str,
        authorized_by: str,
    ) -> AgentFactoryGateSubmission:
        """Apply human authorization override to a gate decision."""
        sub = self._submissions.get(submission_id)
        if not sub:
            raise ValueError(f"Submission not found: {submission_id}")
        if not justification or not authorized_by:
            raise ValueError("justification and authorized_by are required for override")

        sub.verdict = override_verdict
        sub.release_permitted = (override_verdict == AgentFactoryGateVerdict.READY_FOR_PRODUCTION)
        sub.conditions.append(
            f"Override applied by {authorized_by}: {justification}"
        )
        return sub

    def get_pending_submissions(self) -> List[AgentFactoryGateSubmission]:
        """Return submissions waiting for evaluation."""
        return [
            s
            for s in self._submissions.values()
            if s.verdict == AgentFactoryGateVerdict.INSUFFICIENT_EVALUATION
        ]

    def get_agent_gating_history(self, agent_id: str) -> List[AgentFactoryGateSubmission]:
        """Return all gating submissions for an agent."""
        return [s for s in self._submissions.values() if s.agent_id == agent_id]

    def get_failing_criteria_summary(self) -> Dict[str, int]:
        """Count failures per evaluation criterion across all submissions."""
        summary: Dict[str, int] = {}
        for sub in self._submissions.values():
            for c in sub.checks:
                if not c.passed:
                    crit_name = c.criterion.value
                    summary[crit_name] = summary.get(crit_name, 0) + 1
        return summary

    def get_production_admissibility_report(self) -> Dict[str, Any]:
        """Generate aggregate release admissibility metrics."""
        total = len(self._submissions)
        ready = sum(
            1 for s in self._submissions.values() if s.verdict == AgentFactoryGateVerdict.READY_FOR_PRODUCTION
        )
        staging = sum(
            1 for s in self._submissions.values() if s.verdict == AgentFactoryGateVerdict.CONDITIONAL_STAGING
        )
        rejected = sum(
            1 for s in self._submissions.values() if s.verdict == AgentFactoryGateVerdict.REJECTED_UNSAFE
        )
        pass_rate = round(ready / total, 4) if total > 0 else 0.0

        return {
            "total_submissions": total,
            "ready_for_production": ready,
            "conditional_staging": staging,
            "rejected_unsafe": rejected,
            "production_pass_rate": pass_rate,
        }
