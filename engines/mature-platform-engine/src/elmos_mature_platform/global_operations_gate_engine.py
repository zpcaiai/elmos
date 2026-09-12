"""Global Operations Gate Engine (Batch 39 - Skill 1360).

Central operational gate controlling release promotion across production and staging,
validating SLO burn, change freezes, on-call assignments, open P1/P2 incidents,
and disaster recovery compliance.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import uuid

from elmos_mature_platform.types import (
    GateCheckCategory,
    GateVerdict,
    GlobalOperationsGateDecision,
    OperationsGateCheck,
)


class GlobalOperationsGateEngine:
    """Industrial operations gate engine for release certification (B39)."""

    def __init__(self):
        self._decisions: Dict[str, GlobalOperationsGateDecision] = {}
        self._change_freezes: Dict[str, Dict[str, Any]] = {}
        self._audit_log: List[Dict[str, Any]] = []

    def set_change_freeze(
        self,
        environment: str,
        active: bool,
        reason: str = "",
        set_by: str = "sre-lead",
    ) -> None:
        """Set or clear a change freeze on an environment."""
        self._change_freezes[environment] = {
            "active": active,
            "reason": reason,
            "set_by": set_by,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        self._record_audit("change_freeze_updated", environment, {"active": active, "reason": reason})

    def is_change_freeze_active(self, environment: str) -> bool:
        """Check if change freeze is currently active on environment."""
        freeze = self._change_freezes.get(environment)
        return bool(freeze and freeze.get("active"))

    def create_gate_request(
        self,
        release_id: str,
        target_environment: str = "production",
    ) -> GlobalOperationsGateDecision:
        """Initiate a new gate decision workflow for a release."""
        decision_id = f"gate-{uuid.uuid4().hex[:8]}"
        decision = GlobalOperationsGateDecision(
            decision_id=decision_id,
            release_id=release_id,
            target_environment=target_environment,
            overall_verdict=GateVerdict.REJECTED,
            checks=[],
            approved_by="",
            emergency_override=False,
            override_reason="",
            timestamp=datetime.now(timezone.utc).isoformat(),
        )

        # Automatically add change freeze check
        is_frozen = self.is_change_freeze_active(target_environment)
        freeze_check = OperationsGateCheck(
            check_id=f"chk-freeze-{uuid.uuid4().hex[:6]}",
            category=GateCheckCategory.CHANGE_FREEZE,
            name="Environment Change Freeze Check",
            passed=not is_frozen,
            current_value=1.0 if is_frozen else 0.0,
            threshold_value=0.0,
            details=f"Freeze active: {is_frozen}" if is_frozen else "No active freeze",
            blocking=True,
        )
        decision.checks.append(freeze_check)

        self._decisions[decision_id] = decision
        self._record_audit("gate_created", decision_id, {"release_id": release_id, "env": target_environment})
        return decision

    def get_decision(self, decision_id: str) -> Optional[GlobalOperationsGateDecision]:
        """Fetch an existing gate decision."""
        return self._decisions.get(decision_id)

    def add_check(
        self,
        decision_id: str,
        check: OperationsGateCheck,
    ) -> GlobalOperationsGateDecision:
        """Add an operational check to the decision."""
        decision = self._get_decision_or_raise(decision_id)
        decision.checks.append(check)
        return decision

    def record_slo_check(
        self,
        decision_id: str,
        service: str,
        current_error_budget_pct: float,
        min_required_pct: float = 20.0,
    ) -> OperationsGateCheck:
        """Convenience method to evaluate and append an SLO health check."""
        passed = current_error_budget_pct >= min_required_pct
        check = OperationsGateCheck(
            check_id=f"chk-slo-{uuid.uuid4().hex[:6]}",
            category=GateCheckCategory.SLO_HEALTH,
            name=f"SLO Error Budget: {service}",
            passed=passed,
            current_value=current_error_budget_pct,
            threshold_value=min_required_pct,
            details=f"Remaining budget {current_error_budget_pct}% vs min {min_required_pct}%",
            blocking=True,
        )
        self.add_check(decision_id, check)
        return check

    def record_incident_check(
        self,
        decision_id: str,
        active_p1_count: int,
        active_p2_count: int,
    ) -> OperationsGateCheck:
        """Evaluate and append open incident check (P1 is blocking, P2 non-blocking)."""
        passed = (active_p1_count == 0)
        check = OperationsGateCheck(
            check_id=f"chk-inc-{uuid.uuid4().hex[:6]}",
            category=GateCheckCategory.PENDING_INCIDENTS,
            name="Open P1 Incidents Zero-Tolerance",
            passed=passed,
            current_value=float(active_p1_count),
            threshold_value=0.0,
            details=f"Active P1: {active_p1_count}, Active P2: {active_p2_count}",
            blocking=True,
        )
        self.add_check(decision_id, check)
        return check

    def record_oncall_check(
        self,
        decision_id: str,
        primary_oncall: str,
        secondary_oncall: str = "",
    ) -> OperationsGateCheck:
        """Check whether designated primary oncall engineer is staffed."""
        passed = bool(primary_oncall.strip())
        check = OperationsGateCheck(
            check_id=f"chk-oncall-{uuid.uuid4().hex[:6]}",
            category=GateCheckCategory.ONCALL_ROSTER,
            name="On-call Roster Verification",
            passed=passed,
            current_value=1.0 if passed else 0.0,
            threshold_value=1.0,
            details=f"Primary: {primary_oncall or 'None'}, Secondary: {secondary_oncall or 'None'}",
            blocking=True,
        )
        self.add_check(decision_id, check)
        return check

    def evaluate_gate(
        self,
        decision_id: str,
        emergency_override: bool = False,
        approver: str = "",
        override_reason: str = "",
    ) -> GlobalOperationsGateDecision:
        """Evaluate all checks and determine overall gate verdict."""
        decision = self._get_decision_or_raise(decision_id)
        decision.timestamp = datetime.now(timezone.utc).isoformat()

        if emergency_override:
            if not approver or not override_reason:
                raise ValueError("Emergency override requires approver identity and detailed justification")
            decision.overall_verdict = GateVerdict.OVERRIDE_APPROVED
            decision.approved_by = approver
            decision.emergency_override = True
            decision.override_reason = override_reason
            self._record_audit("emergency_override", decision_id, {"approver": approver, "reason": override_reason})
            return decision

        blocking_fails = [c for c in decision.checks if c.blocking and not c.passed]
        non_blocking_fails = [c for c in decision.checks if not c.blocking and not c.passed]

        if blocking_fails:
            decision.overall_verdict = GateVerdict.REJECTED
            decision.approved_by = ""
        elif non_blocking_fails:
            decision.overall_verdict = GateVerdict.CONDITIONAL_APPROVAL
            decision.approved_by = approver or "ops-gate-engine"
        else:
            decision.overall_verdict = GateVerdict.APPROVED
            decision.approved_by = approver or "ops-gate-engine"

        self._record_audit("gate_evaluated", decision_id, {"verdict": decision.overall_verdict.value})
        return decision

    def get_gate_summary(self) -> Dict[str, Any]:
        """Aggregate metrics on gate decisions."""
        total = len(self._decisions)
        verdicts: Dict[str, int] = {}
        for d in self._decisions.values():
            v = d.overall_verdict.value
            verdicts[v] = verdicts.get(v, 0) + 1

        approved = verdicts.get(GateVerdict.APPROVED.value, 0) + verdicts.get(GateVerdict.OVERRIDE_APPROVED.value, 0)
        pass_rate = round((approved / total) * 100.0, 2) if total > 0 else 100.0

        return {
            "total_decisions": total,
            "verdicts": verdicts,
            "approval_rate_pct": pass_rate,
            "active_freezes": {env: data["reason"] for env, data in self._change_freezes.items() if data.get("active")},
        }

    def _get_decision_or_raise(self, decision_id: str) -> GlobalOperationsGateDecision:
        if decision_id not in self._decisions:
            raise ValueError(f"Gate decision {decision_id} not found")
        return self._decisions[decision_id]

    def _record_audit(self, action: str, target: str, details: Dict[str, Any]) -> None:
        self._audit_log.append({
            "action": action,
            "target": target,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "details": details,
        })

    def get_audit_log(self) -> List[Dict[str, Any]]:
        return list(self._audit_log)
