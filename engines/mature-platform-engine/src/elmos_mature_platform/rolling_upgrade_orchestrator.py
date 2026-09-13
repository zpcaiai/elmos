import time
import uuid
from datetime import datetime, timezone
from typing import Dict, List, Optional, Set

from elmos_mature_platform.types import (
    CanaryDecision,
    CanaryObservation,
    CanaryWaveSpec,
    DrainingStatus,
    RollbackRecord,
    RollingUpgradePlan,
)


class RollingUpgradeOrchestrator:
    """Orchestrates zero-downtime rolling upgrades using canary waves."""

    def __init__(self):
        self._plans: Dict[str, RollingUpgradePlan] = {}
        self._active_plan_id: Optional[str] = None
        self._plan_status: Dict[str, Dict] = {}
        self._history: List[Dict] = []
        self._rollbacks: Dict[str, RollbackRecord] = {}

    def create_upgrade_plan(
        self, source: str, target: str, wave_specs: List[CanaryWaveSpec]
    ) -> RollingUpgradePlan:
        """Create a new rolling upgrade plan with validated canary waves."""
        if not wave_specs:
            raise ValueError("Upgrade plan must have at least one canary wave.")
        
        sorted_waves = sorted(wave_specs, key=lambda w: w.traffic_percentage)
        for i, wave in enumerate(sorted_waves):
            if wave.traffic_percentage <= 0 or wave.traffic_percentage > 100:
                raise ValueError(f"Invalid traffic percentage: {wave.traffic_percentage}")
            if i > 0 and wave.traffic_percentage <= sorted_waves[i - 1].traffic_percentage:
                raise ValueError("Traffic percentages must be strictly increasing.")
        
        if sorted_waves[-1].traffic_percentage != 100.0:
            raise ValueError("Final wave must have 100.0 traffic percentage.")

        if self._active_plan_id is not None:
            raise RuntimeError("An upgrade plan is already active.")

        plan_id = f"plan-{uuid.uuid4()}"
        plan = RollingUpgradePlan(
            plan_id=plan_id,
            source_version=source,
            target_version=target,
            waves=sorted_waves,
        )
        self._plans[plan_id] = plan
        self._plan_status[plan_id] = {
            "phase": "CREATED",
            "completed_waves": [],
            "pending_waves": [w.wave_number for w in sorted_waves],
            "active_instances": {"source": 100, "target": 0},
            "source_version": source,
            "target_version": target,
        }
        return plan

    def initiate_upgrade(self, plan_id: str) -> str:
        """Initiate the upgrade process for a given plan."""
        if plan_id not in self._plans:
            raise ValueError(f"Plan {plan_id} not found.")
        
        if self._active_plan_id is not None and self._active_plan_id != plan_id:
            raise RuntimeError("Another upgrade plan is currently active.")
            
        self._active_plan_id = plan_id
        status = self._plan_status[plan_id]
        status["phase"] = "IN_PROGRESS"
        # Register initial target instances
        status["active_instances"]["target"] = 1
        
        return "Upgrade initiated successfully."

    def evaluate_wave_gate(
        self, observation: CanaryObservation, wave: CanaryWaveSpec
    ) -> CanaryDecision:
        """Evaluate observation against SLO thresholds for a wave."""
        if observation.error_rate > wave.max_error_rate:
            return CanaryDecision.ROLLBACK
        if observation.p99_latency_ms > wave.max_p99_latency_ms:
            return CanaryDecision.ROLLBACK
        return CanaryDecision.PROCEED

    def execute_canary_wave(
        self, plan_id: str, wave: CanaryWaveSpec, observation: CanaryObservation
    ) -> CanaryDecision:
        """Execute and evaluate a single canary wave."""
        if plan_id not in self._plans:
            raise ValueError(f"Plan {plan_id} not found.")
            
        plan = self._plans[plan_id]
        status = self._plan_status[plan_id]
        
        if status["phase"] != "IN_PROGRESS":
            raise RuntimeError(f"Cannot execute wave in phase: {status['phase']}")
            
        if wave.wave_number not in status["pending_waves"]:
            raise ValueError(f"Wave {wave.wave_number} is not pending.")

        decision = self.evaluate_wave_gate(observation, wave)
        
        if decision == CanaryDecision.ROLLBACK:
            if plan.auto_rollback_on_breach:
                self.trigger_rollback(plan_id, f"SLO breach in wave {wave.wave_number}")
                return CanaryDecision.ROLLBACK
            else:
                return CanaryDecision.HOLD
                
        if decision == CanaryDecision.PROCEED:
            status["pending_waves"].remove(wave.wave_number)
            status["completed_waves"].append(wave.wave_number)
            # Adjust instances based on traffic
            target_instances = int((wave.traffic_percentage / 100.0) * 100)
            source_instances = 100 - target_instances
            status["active_instances"]["target"] = target_instances
            status["active_instances"]["source"] = source_instances
            
        return decision

    def drain_instances(self, instance_ids: List[str], timeout_s: float) -> List[DrainingStatus]:
        """Simulate graceful connection draining for instances."""
        results = []
        for instance_id in instance_ids:
            # Simulate a draining scenario: half succeed quickly, half might timeout if timeout_s is too small
            # For simplicity, we just use the timeout_s to determine if it succeeds
            success = timeout_s >= 5.0
            results.append(
                DrainingStatus(
                    instance_id=instance_id,
                    deregistered=True,
                    inflight_requests=0 if success else 5,
                    drained_successfully=success,
                    elapsed_seconds=min(5.0, timeout_s),
                )
            )
        return results

    def trigger_rollback(self, plan_id: str, reason: str) -> RollbackRecord:
        """Instant rollback to source version."""
        if plan_id not in self._plans:
            raise ValueError(f"Plan {plan_id} not found.")
            
        plan = self._plans[plan_id]
        status = self._plan_status[plan_id]
        
        status["phase"] = "ROLLED_BACK"
        status["active_instances"]["target"] = 0
        status["active_instances"]["source"] = 100
        
        record = RollbackRecord(
            rollback_id=f"rb-{uuid.uuid4()}",
            plan_id=plan_id,
            trigger_reason=reason,
            initiated_at=datetime.now(timezone.utc).isoformat(),
            completed_at=datetime.now(timezone.utc).isoformat(),
            rollback_duration_ms=150.0,
            restored_version=plan.source_version,
            success=True,
        )
        self._rollbacks[plan_id] = record
        self._history.append({"plan_id": plan_id, "status": "ROLLED_BACK"})
        self._active_plan_id = None
        return record

    def complete_upgrade(self, plan_id: str) -> Dict:
        """Mark upgrade as complete after all waves pass."""
        if plan_id not in self._plans:
            raise ValueError(f"Plan {plan_id} not found.")
            
        status = self._plan_status[plan_id]
        if status["pending_waves"]:
            raise RuntimeError("Cannot complete upgrade with pending waves.")
            
        status["phase"] = "COMPLETED"
        status["active_instances"]["target"] = 100
        status["active_instances"]["source"] = 0
        
        self._history.append({"plan_id": plan_id, "status": "COMPLETED"})
        self._active_plan_id = None
        return status

    def get_upgrade_status(self, plan_id: str) -> Dict:
        """Get the current status of an upgrade plan."""
        if plan_id not in self._plan_status:
            raise ValueError(f"Plan {plan_id} not found.")
        return self._plan_status[plan_id]

    def list_upgrade_history(self) -> List[Dict]:
        """List completed/rolled-back upgrades."""
        return list(self._history)

    def validate_expand_contract_schema(
        self, old_cols: List[str], new_cols: List[str], removed_cols: List[str]
    ) -> Dict:
        """Ensure no premature column removal during expand/contract migrations."""
        if not self._active_plan_id:
            # If no upgrade active, removing is technically fine, but expand_contract might be independent.
            # Usually expand_contract ensures no removed_cols if old version is active.
            # Assuming old version is always active if there's an active plan or just checking removed_cols logic.
            pass

        if self._active_plan_id:
            status = self._plan_status[self._active_plan_id]
            if status["active_instances"]["source"] > 0 and removed_cols:
                raise ValueError("Cannot remove columns while old version instances are still active.")

        return {
            "valid": True,
            "old_cols": old_cols,
            "new_cols": new_cols,
            "removed_cols": removed_cols,
        }
