"""Runner Version Compatibility Engine (Batch 38 - Skill 1339).

Enforces N-1, N, N+1 runner agent version compatibility, protocol negotiation,
capability discovery, fleet drain/upgrade coordination, and fail-closed admission.
"""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import re
from typing import Any, Dict, List, Optional, Set, Tuple

from elmos_mature_platform.types import (
    CompatibilityCheckResult,
    RunnerCapability,
    RunnerDrainUpgradePlan,
    RunnerProtocolVersion,
    RunnerRegistration,
    RunnerStatus,
)


def _parse_semver(v_str: str) -> Tuple[int, int, int]:
    """Parse major, minor, patch from version string like '3.2.1' or 'v3.2.1'."""
    clean = v_str.lstrip("v").strip()
    match = re.match(r"^(\d+)\.(\d+)\.(\d+)", clean)
    if not match:
        parts = clean.split(".")
        try:
            major = int(parts[0]) if len(parts) > 0 else 0
            minor = int(parts[1]) if len(parts) > 1 else 0
            patch = int(parts[2]) if len(parts) > 2 else 0
            return (major, minor, patch)
        except ValueError:
            return (0, 0, 0)
    return (int(match.group(1)), int(match.group(2)), int(match.group(3)))


class RunnerVersionCompatibilityEngine:
    """Industrial engine for runner version and protocol compatibility (B38)."""

    def __init__(self, control_plane_version: str = "3.2.0", control_plane_protocol: str = "3.0.0"):
        self.control_plane_version = control_plane_version
        self.control_plane_protocol = control_plane_protocol
        self._runners: Dict[str, RunnerRegistration] = {}
        self._upgrade_plans: Dict[str, RunnerDrainUpgradePlan] = {}
        self._audit_log: List[Dict[str, Any]] = []

    def register_runner(self, runner: RunnerRegistration) -> RunnerRegistration:
        """Register or update a runner in the fleet."""
        if not runner.last_heartbeat:
            runner.last_heartbeat = datetime.now(timezone.utc).isoformat()
        self._runners[runner.runner_id] = runner
        self._record_audit("runner_registered", runner.runner_id, {"version": runner.runner_version})
        return runner

    def get_runner(self, runner_id: str) -> Optional[RunnerRegistration]:
        """Fetch registered runner by ID."""
        return self._runners.get(runner_id)

    def list_runners(self, status: Optional[RunnerStatus] = None) -> List[RunnerRegistration]:
        """List registered runners, optionally filtered by status."""
        if status:
            return [r for r in self._runners.values() if r.status == status]
        return list(self._runners.values())

    def update_heartbeat(self, runner_id: str, active_jobs: int = 0) -> bool:
        """Update runner heartbeat timestamp and active job count."""
        runner = self._runners.get(runner_id)
        if not runner:
            return False
        runner.last_heartbeat = datetime.now(timezone.utc).isoformat()
        runner.active_jobs_count = active_jobs
        if runner.status == RunnerStatus.DRAINING and active_jobs == 0:
            runner.status = RunnerStatus.DRAINED
            self._record_audit("runner_drained", runner_id, {})
        return True

    def evaluate_compatibility(
        self,
        runner_version: str,
        protocol_version: str,
        required_capabilities: Optional[List[RunnerCapability]] = None,
        runner_capabilities: Optional[List[RunnerCapability]] = None,
    ) -> CompatibilityCheckResult:
        """Evaluate runner compatibility against control plane version and protocol.

        Rules:
        - Major version mismatch -> Incompatible.
        - Same major:
          - Minor delta == 0: Exact match -> Compatible.
          - Minor delta == -1: N-1 version -> Compatible (upgrade suggested).
          - Minor delta == +1: N+1 version -> Compatible (future-ready).
          - Minor delta < -1: Older than N-1 -> Incompatible (too old, upgrade required).
          - Minor delta > +1: Newer than N+1 -> Incompatible (too new).
        - Protocol major mismatch -> Incompatible.
        - Missing required capabilities -> Incompatible.
        """
        cp_maj, cp_min, cp_patch = _parse_semver(self.control_plane_version)
        rn_maj, rn_min, rn_patch = _parse_semver(runner_version)
        proto_cp_maj, _, _ = _parse_semver(self.control_plane_protocol)
        proto_rn_maj, _, _ = _parse_semver(protocol_version)

        # Check protocol compatibility
        if proto_cp_maj != proto_rn_maj:
            return CompatibilityCheckResult(
                compatible=False,
                control_plane_version=self.control_plane_version,
                runner_version=runner_version,
                version_relation="incompatible_protocol",
                upgrade_required=True,
                details=f"Runner protocol major {proto_rn_maj} incompatible with control plane protocol {proto_cp_maj}",
            )

        # Check major version
        if rn_maj != cp_maj:
            return CompatibilityCheckResult(
                compatible=False,
                control_plane_version=self.control_plane_version,
                runner_version=runner_version,
                version_relation="incompatible_major",
                upgrade_required=True,
                details=f"Major version mismatch: runner {rn_maj} vs control plane {cp_maj}",
            )

        # Check minor version relation
        minor_delta = rn_min - cp_min
        if minor_delta == 0:
            relation = "exact"
            compatible = True
            upgrade_req = False
        elif minor_delta == -1:
            relation = "n_minus_1"
            compatible = True
            upgrade_req = False
        elif minor_delta == 1:
            relation = "n_plus_1"
            compatible = True
            upgrade_req = False
        elif minor_delta < -1:
            relation = "too_old"
            compatible = False
            upgrade_req = True
        else:
            relation = "too_new"
            compatible = False
            upgrade_req = False

        # Check capabilities
        unsupported: List[str] = []
        if required_capabilities:
            available = set(runner_capabilities or [])
            for cap in required_capabilities:
                if cap not in available:
                    unsupported.append(cap.value)
            if unsupported:
                compatible = False

        details = f"Relation: {relation}; Minor delta: {minor_delta}."
        if unsupported:
            details += f" Missing capabilities: {', '.join(unsupported)}."

        return CompatibilityCheckResult(
            compatible=compatible,
            control_plane_version=self.control_plane_version,
            runner_version=runner_version,
            version_relation=relation,
            unsupported_capabilities=unsupported,
            upgrade_required=upgrade_req,
            details=details,
        )

    def initiate_drain(self, runner_id: str, timeout_seconds: int = 300) -> Optional[RunnerDrainUpgradePlan]:
        """Initiate graceful drain of a runner for upgrade."""
        runner = self._runners.get(runner_id)
        if not runner:
            return None

        runner.status = RunnerStatus.DRAINING
        runner.drain_requested_at = datetime.now(timezone.utc).isoformat()

        plan_id = f"drain-{runner_id}-{int(datetime.now(timezone.utc).timestamp())}"
        plan = RunnerDrainUpgradePlan(
            plan_id=plan_id,
            runner_id=runner_id,
            current_version=runner.runner_version,
            target_version=self.control_plane_version,
            drain_timeout_seconds=timeout_seconds,
            status="draining" if runner.active_jobs_count > 0 else "ready_for_upgrade",
            created_at=datetime.now(timezone.utc).isoformat(),
        )
        if runner.active_jobs_count == 0:
            runner.status = RunnerStatus.DRAINED

        self._upgrade_plans[plan_id] = plan
        self._record_audit("drain_initiated", runner_id, {"plan_id": plan_id})
        return plan

    def complete_upgrade(self, plan_id: str, new_runner_version: str, new_protocol_version: str) -> bool:
        """Mark upgrade complete and restore runner to active status."""
        plan = self._upgrade_plans.get(plan_id)
        if not plan:
            return False

        runner = self._runners.get(plan.runner_id)
        if not runner:
            return False

        runner.runner_version = new_runner_version
        runner.protocol_version = new_protocol_version
        runner.status = RunnerStatus.ACTIVE
        runner.drain_requested_at = ""

        plan.status = "completed"
        plan.completed_at = datetime.now(timezone.utc).isoformat()
        self._record_audit("upgrade_completed", runner.runner_id, {"new_version": new_runner_version})
        return True

    def get_fleet_compatibility_summary(self) -> Dict[str, Any]:
        """Generate fleet-wide compatibility breakdown."""
        total = len(self._runners)
        compatible_count = 0
        incompatible_count = 0
        upgrade_needed_count = 0
        status_counts: Dict[str, int] = {}

        for runner in self._runners.values():
            status_counts[runner.status.value] = status_counts.get(runner.status.value, 0) + 1
            res = self.evaluate_compatibility(
                runner_version=runner.runner_version,
                protocol_version=runner.protocol_version,
                runner_capabilities=runner.supported_capabilities,
            )
            if res.compatible:
                compatible_count += 1
            else:
                incompatible_count += 1
            if res.upgrade_required:
                upgrade_needed_count += 1

        pct = (compatible_count / total * 100.0) if total > 0 else 100.0
        return {
            "control_plane_version": self.control_plane_version,
            "total_runners": total,
            "compatible_runners": compatible_count,
            "incompatible_runners": incompatible_count,
            "upgrade_required_count": upgrade_needed_count,
            "compatibility_rate_pct": round(pct, 2),
            "status_breakdown": status_counts,
        }

    def _record_audit(self, action: str, runner_id: str, details: Dict[str, Any]) -> None:
        self._audit_log.append({
            "action": action,
            "runner_id": runner_id,
            "details": details,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

    def get_audit_log(self) -> List[Dict[str, Any]]:
        return list(self._audit_log)
