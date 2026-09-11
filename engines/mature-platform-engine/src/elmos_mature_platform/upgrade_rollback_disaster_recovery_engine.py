"""Upgrade Rollback and Disaster Recovery Engine (Batch 38 - Skill 1345).

Manages automated rollback plans, disaster recovery orchestration, drill
verifications, and recovery metrics across enterprise deployment editions.
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import uuid

from .types import (
    DisasterRecoveryDrillRecord,
    DisasterRecoveryStrategy,
    RecoveryPlanStatus,
    RollbackExecutionStep,
    RollbackTriggerType,
    UpgradeRollbackPlan,
)


class UpgradeRollbackDisasterRecoveryEngine:
    """Orchestrates rollback workflows and disaster recovery validation."""

    def __init__(self) -> None:
        self._plans: Dict[str, UpgradeRollbackPlan] = {}
        self._drills: Dict[str, DisasterRecoveryDrillRecord] = {}

    def create_rollback_plan(self, plan: UpgradeRollbackPlan) -> str:
        """Create and register an upgrade rollback plan."""
        if not plan.plan_id:
            plan.plan_id = f"plan-{uuid.uuid4().hex[:8]}"
        if not plan.deployment_id:
            raise ValueError("deployment_id is required")
        if plan.target_version == plan.rollback_version:
            raise ValueError("target_version and rollback_version cannot be identical")

        if not plan.created_at:
            plan.created_at = datetime.now(timezone.utc).isoformat()

        self._plans[plan.plan_id] = plan
        return plan.plan_id

    def add_execution_step(self, plan_id: str, step: RollbackExecutionStep) -> UpgradeRollbackPlan:
        """Add an execution step to a rollback plan."""
        plan = self._plans.get(plan_id)
        if not plan:
            raise ValueError(f"Plan not found: {plan_id}")

        if not step.step_id:
            step.step_id = f"step-{len(plan.steps) + 1}"
        if not step.order:
            step.order = len(plan.steps) + 1

        plan.steps.append(step)
        plan.steps.sort(key=lambda s: s.order)
        return plan

    def validate_plan(self, plan_id: str) -> bool:
        """Validate that a rollback plan is complete and executable."""
        plan = self._plans.get(plan_id)
        if not plan:
            raise ValueError(f"Plan not found: {plan_id}")

        if not plan.steps:
            return False

        orders = [s.order for s in plan.steps]
        if len(orders) != len(set(orders)):
            return False

        for step in plan.steps:
            if not step.command_ref or not step.target_component:
                return False

        plan.status = RecoveryPlanStatus.VALIDATED
        return True

    def trigger_rollback(
        self, plan_id: str, trigger: RollbackTriggerType, operator: str = ""
    ) -> UpgradeRollbackPlan:
        """Initiate rollback execution for a plan."""
        plan = self._plans.get(plan_id)
        if not plan:
            raise ValueError(f"Plan not found: {plan_id}")

        if plan.status not in (RecoveryPlanStatus.VALIDATED, RecoveryPlanStatus.DRAFT):
            raise ValueError(f"Cannot trigger rollback in status: {plan.status.value}")

        plan.status = RecoveryPlanStatus.EXECUTING
        return plan

    def execute_step(
        self, plan_id: str, step_id: str, success: bool, error: str = ""
    ) -> RollbackExecutionStep:
        """Record outcome of executing a single rollback step."""
        plan = self._plans.get(plan_id)
        if not plan:
            raise ValueError(f"Plan not found: {plan_id}")

        step = next((s for s in plan.steps if s.step_id == step_id), None)
        if not step:
            raise ValueError(f"Step not found: {step_id}")

        step.executed_at = datetime.now(timezone.utc).isoformat()
        if success:
            step.status = "completed"
            step.error_message = ""
        else:
            step.status = "failed"
            step.error_message = error

        return step

    def finalize_rollback(
        self, plan_id: str, actual_downtime_seconds: int, data_loss_detected: bool = False
    ) -> UpgradeRollbackPlan:
        """Finalize the rollback procedure and establish success or failure."""
        plan = self._plans.get(plan_id)
        if not plan:
            raise ValueError(f"Plan not found: {plan_id}")

        if plan.status != RecoveryPlanStatus.EXECUTING:
            raise ValueError(f"Cannot finalize plan in status: {plan.status.value}")

        plan.completed_at = datetime.now(timezone.utc).isoformat()
        plan.actual_downtime_seconds = actual_downtime_seconds
        plan.data_loss_detected = data_loss_detected

        any_failed = any(s.status == "failed" for s in plan.steps)
        all_completed = all(s.status == "completed" for s in plan.steps)

        if any_failed or not all_completed:
            plan.status = RecoveryPlanStatus.FAILED
        else:
            plan.status = RecoveryPlanStatus.COMPLETED

        return plan

    def record_dr_drill(self, drill: DisasterRecoveryDrillRecord) -> str:
        """Record and evaluate a disaster recovery drill."""
        if not drill.drill_id:
            drill.drill_id = f"drill-{uuid.uuid4().hex[:8]}"
        if not drill.drill_timestamp:
            drill.drill_timestamp = datetime.now(timezone.utc).isoformat()

        drill.passed = (
            drill.rto_seconds <= drill.target_rto_seconds
            and drill.rpo_seconds <= drill.target_rpo_seconds
        )
        self._drills[drill.drill_id] = drill
        return drill.drill_id

    def evaluate_drill_compliance(self, drill_id: str) -> bool:
        """Return whether the DR drill complied with target RTO and RPO."""
        drill = self._drills.get(drill_id)
        if not drill:
            raise ValueError(f"Drill not found: {drill_id}")
        return drill.passed

    def get_active_recovery_plans(self) -> List[UpgradeRollbackPlan]:
        """Return plans currently validated or actively executing."""
        return [
            p
            for p in self._plans.values()
            if p.status in (RecoveryPlanStatus.VALIDATED, RecoveryPlanStatus.EXECUTING)
        ]

    def get_rollback_metrics(self) -> Dict[str, Any]:
        """Compute summary statistics for rollback executions."""
        total = len(self._plans)
        if total == 0:
            return {
                "total_plans": 0,
                "completed_count": 0,
                "failed_count": 0,
                "success_rate": 0.0,
                "avg_downtime_seconds": 0.0,
                "data_loss_incidents": 0,
            }

        completed = sum(1 for p in self._plans.values() if p.status == RecoveryPlanStatus.COMPLETED)
        failed = sum(1 for p in self._plans.values() if p.status == RecoveryPlanStatus.FAILED)
        data_loss = sum(1 for p in self._plans.values() if p.data_loss_detected)
        downtimes = [
            p.actual_downtime_seconds
            for p in self._plans.values()
            if p.status == RecoveryPlanStatus.COMPLETED
        ]
        avg_downtime = (sum(downtimes) / len(downtimes)) if downtimes else 0.0

        return {
            "total_plans": total,
            "completed_count": completed,
            "failed_count": failed,
            "success_rate": round(completed / total, 4),
            "avg_downtime_seconds": round(avg_downtime, 2),
            "data_loss_incidents": data_loss,
        }
