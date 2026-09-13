import hashlib
from datetime import datetime, timezone
from typing import Dict, List, Optional

from elmos_mature_platform.types import (
    FeatureFlag,
    FlagState,
    FlagLifecycleStage,
    FlagEvaluation,
    FlagAuditEntry,
)


class FeatureFlagGovernanceEngine:
    """
    Engine for governing feature flags, progressive rollouts, and kill switches.
    """

    def __init__(self):
        self._flags: Dict[str, FeatureFlag] = {}
        self._audit_trails: Dict[str, List[FlagAuditEntry]] = {}

    def _log_audit(self, flag_id: str, action: str, actor: str, previous_state: str, new_state: str, reason: str = "") -> None:
        if flag_id not in self._audit_trails:
            self._audit_trails[flag_id] = []
        
        entry = FlagAuditEntry(
            flag_id=flag_id,
            action=action,
            actor=actor,
            previous_state=previous_state,
            new_state=new_state,
            timestamp=datetime.now(timezone.utc).isoformat(),
            reason=reason
        )
        self._audit_trails[flag_id].append(entry)

    def create_flag(self, flag: FeatureFlag) -> None:
        """
        Creates a new feature flag.
        """
        if flag.flag_id in self._flags:
            raise ValueError(f"Flag {flag.flag_id} already exists.")
        
        # Validate dependencies exist (basic check)
        for dep_id in flag.dependencies:
            if dep_id not in self._flags:
                raise ValueError(f"Dependency flag {dep_id} does not exist.")

        self._flags[flag.flag_id] = flag
        self._log_audit(
            flag_id=flag.flag_id,
            action="created",
            actor=flag.owner,
            previous_state="",
            new_state=flag.state.value,
            reason="Flag creation"
        )

    def _get_flag(self, flag_id: str) -> FeatureFlag:
        if flag_id not in self._flags:
            raise ValueError(f"Flag {flag_id} not found.")
        return self._flags[flag_id]

    def _is_flag_enabled_recursively(self, flag_id: str) -> bool:
        flag = self._get_flag(flag_id)
        if flag.state != FlagState.ENABLED:
            return False
        for dep_id in flag.dependencies:
            if not self._is_flag_enabled_recursively(dep_id):
                return False
        return True

    def check_dependency_order(self, flag_id: str) -> Dict[str, bool]:
        """
        Check if all dependency flags are enabled before this one can be enabled.
        Returns a dict of dependency_id -> is_enabled.
        """
        flag = self._get_flag(flag_id)
        result = {}
        for dep_id in flag.dependencies:
            result[dep_id] = self._is_flag_enabled_recursively(dep_id)
        return result

    def evaluate(self, flag_id: str, tenant_id: str) -> FlagEvaluation:
        """
        Evaluates a flag for a tenant:
        - Checks kill switch first
        - Then targeted tenants
        - Then percentage
        - Then global state
        """
        flag = self._get_flag(flag_id)
        
        now_str = datetime.now(timezone.utc).isoformat()

        if flag.lifecycle == FlagLifecycleStage.RETIRED:
            return FlagEvaluation(flag_id=flag_id, tenant_id=tenant_id, enabled=False, reason="retired", evaluated_at=now_str)

        if flag.state == FlagState.KILL_SWITCHED:
            return FlagEvaluation(flag_id=flag_id, tenant_id=tenant_id, enabled=False, reason="kill_switched", evaluated_at=now_str)

        if flag.state == FlagState.DISABLED:
            return FlagEvaluation(flag_id=flag_id, tenant_id=tenant_id, enabled=False, reason="disabled", evaluated_at=now_str)

        if flag.state == FlagState.ENABLED:
            return FlagEvaluation(flag_id=flag_id, tenant_id=tenant_id, enabled=True, reason="global", evaluated_at=now_str)

        if flag.state == FlagState.TENANT_TARGETED:
            if tenant_id in flag.targeted_tenants:
                return FlagEvaluation(flag_id=flag_id, tenant_id=tenant_id, enabled=True, reason="targeted", evaluated_at=now_str)
            return FlagEvaluation(flag_id=flag_id, tenant_id=tenant_id, enabled=False, reason="targeted_miss", evaluated_at=now_str)

        if flag.state == FlagState.PERCENTAGE_ROLLOUT:
            if tenant_id in flag.targeted_tenants:
                return FlagEvaluation(flag_id=flag_id, tenant_id=tenant_id, enabled=True, reason="targeted", evaluated_at=now_str)

            # Deterministic hash for percentage rollout
            hash_input = f"{tenant_id}{flag_id}".encode("utf-8")
            hash_val = int(hashlib.md5(hash_input).hexdigest(), 16)
            percentage_bucket = hash_val % 100

            if percentage_bucket < flag.rollout_percentage:
                return FlagEvaluation(flag_id=flag_id, tenant_id=tenant_id, enabled=True, reason="percentage", evaluated_at=now_str)
            return FlagEvaluation(flag_id=flag_id, tenant_id=tenant_id, enabled=False, reason="percentage_miss", evaluated_at=now_str)

        return FlagEvaluation(flag_id=flag_id, tenant_id=tenant_id, enabled=False, reason="unknown", evaluated_at=now_str)

    def set_percentage_rollout(self, flag_id: str, percentage: float, actor: str) -> None:
        """
        Updates flag to percentage rollout (0-100).
        """
        if not (0 <= percentage <= 100):
            raise ValueError("Percentage must be between 0 and 100.")
            
        flag = self._get_flag(flag_id)
        if flag.state == FlagState.KILL_SWITCHED:
            raise ValueError("Cannot modify a kill-switched flag.")
            
        if flag.lifecycle == FlagLifecycleStage.RETIRED:
            raise ValueError("Cannot modify a retired flag.")

        deps_status = self.check_dependency_order(flag_id)
        if not all(deps_status.values()):
            raise ValueError("Cannot roll out flag, dependencies not fully enabled.")

        prev_state = flag.state.value
        flag.state = FlagState.PERCENTAGE_ROLLOUT
        flag.rollout_percentage = percentage
        flag.lifecycle = FlagLifecycleStage.ROLLING_OUT

        self._log_audit(
            flag_id=flag_id,
            action="updated_rollout_percentage",
            actor=actor,
            previous_state=prev_state,
            new_state=flag.state.value,
            reason=f"Set rollout percentage to {percentage}%"
        )

    def add_targeted_tenant(self, flag_id: str, tenant_id: str, actor: str) -> None:
        """
        Adds a tenant to the targeted tenants list.
        Sets state to TENANT_TARGETED if it's currently DISABLED or CREATED.
        """
        flag = self._get_flag(flag_id)
        if flag.state == FlagState.KILL_SWITCHED:
            raise ValueError("Cannot modify a kill-switched flag.")
        if flag.lifecycle == FlagLifecycleStage.RETIRED:
            raise ValueError("Cannot modify a retired flag.")

        deps_status = self.check_dependency_order(flag_id)
        if not all(deps_status.values()):
            raise ValueError("Cannot target tenants, dependencies not fully enabled.")

        if tenant_id not in flag.targeted_tenants:
            flag.targeted_tenants.append(tenant_id)
            
        prev_state = flag.state.value
        if flag.state == FlagState.DISABLED:
            flag.state = FlagState.TENANT_TARGETED
            flag.lifecycle = FlagLifecycleStage.TESTING

        self._log_audit(
            flag_id=flag_id,
            action="added_targeted_tenant",
            actor=actor,
            previous_state=prev_state,
            new_state=flag.state.value,
            reason=f"Targeted tenant {tenant_id}"
        )

    def remove_targeted_tenant(self, flag_id: str, tenant_id: str, actor: str) -> None:
        """
        Removes a tenant from targeting.
        """
        flag = self._get_flag(flag_id)
        if flag.state == FlagState.KILL_SWITCHED:
            raise ValueError("Cannot modify a kill-switched flag.")
        if flag.lifecycle == FlagLifecycleStage.RETIRED:
            raise ValueError("Cannot modify a retired flag.")

        if tenant_id in flag.targeted_tenants:
            flag.targeted_tenants.remove(tenant_id)
            self._log_audit(
                flag_id=flag_id,
                action="removed_targeted_tenant",
                actor=actor,
                previous_state=flag.state.value,
                new_state=flag.state.value,
                reason=f"Removed target tenant {tenant_id}"
            )

    def enable_globally(self, flag_id: str, actor: str) -> None:
        """
        Enables the flag for all tenants.
        """
        flag = self._get_flag(flag_id)
        if flag.state == FlagState.KILL_SWITCHED:
            raise ValueError("Cannot enable a kill-switched flag.")
        if flag.lifecycle == FlagLifecycleStage.RETIRED:
            raise ValueError("Cannot enable a retired flag.")

        deps_status = self.check_dependency_order(flag_id)
        if not all(deps_status.values()):
            raise ValueError("Cannot enable flag, dependencies not fully enabled.")

        prev_state = flag.state.value
        flag.state = FlagState.ENABLED
        flag.lifecycle = FlagLifecycleStage.FULLY_ENABLED
        flag.rollout_percentage = 100.0

        self._log_audit(
            flag_id=flag_id,
            action="enabled",
            actor=actor,
            previous_state=prev_state,
            new_state=flag.state.value,
            reason="Enabled globally"
        )

    def kill_switch(self, flag_id: str, reason: str, actor: str) -> None:
        """
        Emergency kill switch. Immediately disables the flag.
        """
        flag = self._get_flag(flag_id)
        prev_state = flag.state.value
        flag.state = FlagState.KILL_SWITCHED
        flag.kill_switch_reason = reason

        self._log_audit(
            flag_id=flag_id,
            action="kill_switched",
            actor=actor,
            previous_state=prev_state,
            new_state=flag.state.value,
            reason=reason
        )

    def retire_flag(self, flag_id: str, actor: str) -> None:
        """
        Marks flag as retired.
        """
        flag = self._get_flag(flag_id)
        prev_state = flag.state.value
        
        flag.state = FlagState.DISABLED
        flag.lifecycle = FlagLifecycleStage.RETIRED

        self._log_audit(
            flag_id=flag_id,
            action="retired",
            actor=actor,
            previous_state=prev_state,
            new_state=flag.state.value,
            reason="Flag retired"
        )

    def detect_stale_flags(self, current_time: str) -> List[FeatureFlag]:
        """
        Detect flags older than stale_after_days that are not FULLY_ENABLED or RETIRED.
        """
        stale_flags = []
        current_dt = datetime.fromisoformat(current_time.replace("Z", "+00:00"))

        for flag in self._flags.values():
            if flag.lifecycle in (FlagLifecycleStage.FULLY_ENABLED, FlagLifecycleStage.RETIRED):
                continue
                
            if not flag.created_at:
                continue
                
            try:
                created_dt = datetime.fromisoformat(flag.created_at.replace("Z", "+00:00"))
                days_old = (current_dt - created_dt).days
                if days_old > flag.stale_after_days:
                    stale_flags.append(flag)
            except ValueError:
                pass
                
        return stale_flags

    def get_audit_trail(self, flag_id: str) -> List[FlagAuditEntry]:
        """
        Returns audit trail for a flag.
        """
        if flag_id not in self._flags:
            raise ValueError(f"Flag {flag_id} not found.")
        return self._audit_trails.get(flag_id, [])

    def get_flag_report(self) -> Dict:
        """
        Summary report: total flags, by state, stale count, kill-switched count
        """
        report = {
            "total_flags": len(self._flags),
            "by_state": {},
            "by_lifecycle": {},
            "stale_count": 0,
            "kill_switched_count": 0
        }

        now_str = datetime.now(timezone.utc).isoformat()
        stale_flags = self.detect_stale_flags(now_str)
        report["stale_count"] = len(stale_flags)

        for flag in self._flags.values():
            state_val = flag.state.value
            lifecycle_val = flag.lifecycle.value
            
            report["by_state"][state_val] = report["by_state"].get(state_val, 0) + 1
            report["by_lifecycle"][lifecycle_val] = report["by_lifecycle"].get(lifecycle_val, 0) + 1
            
            if flag.state == FlagState.KILL_SWITCHED:
                report["kill_switched_count"] += 1

        return report
