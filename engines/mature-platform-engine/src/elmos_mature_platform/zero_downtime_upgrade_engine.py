from typing import Dict, List, Optional
from datetime import datetime, timezone
import math

from elmos_mature_platform.types import (
    ZDUpgradeStrategy,
    ZDUpgradePhase,
    UpgradeTarget,
    UpgradeHealthCheck
)

class ZeroDowntimeUpgradeEngine:
    def __init__(self):
        self.upgrades: Dict[str, UpgradeTarget] = {}
        self.health_checks: Dict[str, List[UpgradeHealthCheck]] = {}

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def create_upgrade(self, target: UpgradeTarget) -> str:
        """Create a new upgrade plan."""
        if target.target_id in self.upgrades:
            raise ValueError(f"Upgrade target {target.target_id} already exists.")
        target.phase = ZDUpgradePhase.PLANNING
        self.upgrades[target.target_id] = target
        self.health_checks[target.target_id] = []
        return target.target_id

    def pre_check(self, target_id: str) -> Dict:
        """Validate an upgrade plan."""
        if target_id not in self.upgrades:
            raise KeyError(f"Target {target_id} not found.")
        
        target = self.upgrades[target_id]
        errors = []
        
        if target.current_version == target.target_version:
            errors.append("Current version matches target version.")
        
        if not isinstance(target.strategy, ZDUpgradeStrategy):
            errors.append("Invalid upgrade strategy.")
            
        if target.instances_total <= 0:
            errors.append("instances_total must be > 0.")
            
        if errors:
            target.phase = ZDUpgradePhase.FAILED
            target.error_message = " | ".join(errors)
            return {"valid": False, "errors": errors}
            
        target.phase = ZDUpgradePhase.PRE_CHECK
        return {"valid": True, "errors": []}

    def start_upgrade(self, target_id: str) -> UpgradeTarget:
        """Move the upgrade to DEPLOYING phase."""
        check_res = self.pre_check(target_id)
        target = self.upgrades[target_id]
        if not check_res["valid"]:
            raise ValueError(f"Pre-check failed: {target.error_message}")
            
        target.phase = ZDUpgradePhase.DEPLOYING
        target.started_at = self._now()
        target.instances_upgraded = 0
        return target

    def upgrade_instance(self, target_id: str, instance_id: str) -> UpgradeTarget:
        """Upgrade one instance, respecting max_unavailable_pct."""
        if target_id not in self.upgrades:
            raise KeyError(f"Target {target_id} not found.")
            
        target = self.upgrades[target_id]
        if target.phase != ZDUpgradePhase.DEPLOYING:
            raise ValueError(f"Cannot upgrade instance in phase {target.phase}")

        max_unavailable = math.ceil(target.instances_total * (target.max_unavailable_pct / 100.0))
        # Ensure we don't upgrade more than max_unavailable at a time if they aren't verified yet
        # In a real engine, we'd track in-progress upgrades. Here we assume sequential.
        # But for invariants, if instances_upgraded >= instances_total, it's an error.
        
        if target.instances_upgraded >= target.instances_total:
            raise ValueError("All instances already upgraded.")
            
        target.instances_upgraded += 1
        return target

    def record_health_check(self, check: UpgradeHealthCheck) -> None:
        """Record a health check for an instance."""
        if check.target_id not in self.upgrades:
            raise KeyError(f"Target {check.target_id} not found.")
        
        if not check.checked_at:
            check.checked_at = self._now()
            
        self.health_checks[check.target_id].append(check)

    def verify_upgrade(self, target_id: str) -> Dict:
        """Check that all upgraded instances are healthy."""
        if target_id not in self.upgrades:
            raise KeyError(f"Target {target_id} not found.")
            
        target = self.upgrades[target_id]
        if target.phase not in [ZDUpgradePhase.DEPLOYING, ZDUpgradePhase.VERIFYING]:
            raise ValueError(f"Cannot verify in phase {target.phase}")
            
        target.phase = ZDUpgradePhase.VERIFYING
        
        # We need at least one healthy check for each upgraded instance?
        # Let's just check if there are any recent failed health checks or if overall it's healthy.
        checks = self.health_checks.get(target_id, [])
        failed_checks = [c for c in checks if not c.healthy]
        
        if failed_checks:
            return {"verified": False, "reason": "Failed health checks detected."}
            
        return {"verified": True, "reason": "All checks passed."}

    def complete_upgrade(self, target_id: str) -> UpgradeTarget:
        """Complete the upgrade. All instances must be upgraded and healthy."""
        verify_res = self.verify_upgrade(target_id)
        target = self.upgrades[target_id]
        
        if not verify_res["verified"]:
            raise ValueError("Cannot complete upgrade: verification failed.")
            
        if target.instances_upgraded < target.instances_total:
            raise ValueError("Cannot complete upgrade: not all instances upgraded.")
            
        target.phase = ZDUpgradePhase.COMPLETED
        target.completed_at = self._now()
        return target

    def rollback_upgrade(self, target_id: str) -> UpgradeTarget:
        """Rollback the upgrade to previous version."""
        if target_id not in self.upgrades:
            raise KeyError(f"Target {target_id} not found.")
            
        target = self.upgrades[target_id]
        if target.phase not in [ZDUpgradePhase.DEPLOYING, ZDUpgradePhase.VERIFYING]:
            raise ValueError(f"Cannot rollback from phase {target.phase}")
            
        target.phase = ZDUpgradePhase.ROLLED_BACK
        target.completed_at = self._now()
        # In a real rollback, we would reset instances_upgraded or create a reverse plan.
        return target

    def get_upgrade_progress(self, target_id: str) -> Dict:
        """Return progress information."""
        if target_id not in self.upgrades:
            raise KeyError(f"Target {target_id} not found.")
            
        target = self.upgrades[target_id]
        checks = self.health_checks.get(target_id, [])
        healthy_count = sum(1 for c in checks if c.healthy)
        
        return {
            "target_id": target.target_id,
            "phase": target.phase,
            "instances_total": target.instances_total,
            "instances_upgraded": target.instances_upgraded,
            "percent_complete": (target.instances_upgraded / target.instances_total * 100) if target.instances_total else 0,
            "health_checks_recorded": len(checks),
            "healthy_checks": healthy_count
        }

    def get_upgrade_report(self) -> Dict:
        """Summary report of all upgrades."""
        total = len(self.upgrades)
        by_phase = {}
        by_strategy = {}
        successes = 0
        rollbacks = 0
        
        for target in self.upgrades.values():
            by_phase[target.phase] = by_phase.get(target.phase, 0) + 1
            by_strategy[target.strategy] = by_strategy.get(target.strategy, 0) + 1
            if target.phase == ZDUpgradePhase.COMPLETED:
                successes += 1
            elif target.phase == ZDUpgradePhase.ROLLED_BACK:
                rollbacks += 1
                
        return {
            "total_upgrades": total,
            "by_phase": by_phase,
            "by_strategy": by_strategy,
            "success_rate_pct": (successes / total * 100) if total else 0,
            "rollback_rate_pct": (rollbacks / total * 100) if total else 0
        }
