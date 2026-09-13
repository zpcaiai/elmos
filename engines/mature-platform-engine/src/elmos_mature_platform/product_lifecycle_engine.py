"""Product Lifecycle Engine module."""

from typing import Any, Dict, List, Optional, Tuple

from elmos_mature_platform.types import (
    ApiChangeType,
    ApiCompatibilityCheck,
    DeprecationRecord,
    ReleaseCandidate,
    ReleaseChannel,
    SupportPolicy,
    SupportStatus,
)


class ProductLifecycleEngine:
    """Engine for Product Lifecycle."""

    def __init__(self) -> None:
        """Empty registries for API surfaces, deprecations, release candidates, support policies, compatibility checks."""
        self.api_surfaces: Dict[str, Any] = {}
        self.deprecations: Dict[str, DeprecationRecord] = {}
        self.release_candidates: Dict[str, ReleaseCandidate] = {}
        self.support_policies: Dict[str, SupportPolicy] = {}
        self.compatibility_checks: Dict[str, ApiCompatibilityCheck] = {}

    def check_api_compatibility(self, api_surface: str, from_version: str, to_version: str, changes: List[Dict[str, Any]]) -> ApiCompatibilityCheck:
        """Analyze changes for breaking/non-breaking. A change with type='removal' or type='breaking' makes backward_compatible=False."""
        breaking_count = 0
        backward_compatible = True
        
        for change in changes:
            ctype = change.get("type")
            if ctype in (ApiChangeType.REMOVAL, ApiChangeType.BREAKING, "removal", "breaking"):
                backward_compatible = False
                breaking_count += 1
                
        check = ApiCompatibilityCheck(
            check_id=f"chk_{api_surface}_{from_version}_{to_version}",
            api_surface=api_surface,
            from_version=from_version,
            to_version=to_version,
            changes=changes,
            breaking_changes_count=breaking_count,
            backward_compatible=backward_compatible,
            forward_compatible=False
        )
        self.compatibility_checks[check.check_id] = check
        return check

    def register_deprecation(self, deprecation: DeprecationRecord) -> None:
        """Track deprecation."""
        self.deprecations[deprecation.deprecation_id] = deprecation

    def get_active_deprecations(self, current_version: str) -> List[DeprecationRecord]:
        """Return deprecations where removal_target > current_version."""
        return [d for d in self.deprecations.values() if d.removal_target > current_version]

    def create_release_candidate(self, version: str, channel: ReleaseChannel, build_sha: str, gate_names: List[str]) -> ReleaseCandidate:
        """Create RC with all gates initially False."""
        gates = {g: False for g in gate_names}
        rc = ReleaseCandidate(
            rc_id=f"rc_{version}_{build_sha[:7]}",
            version=version,
            channel=channel,
            build_sha=build_sha,
            gates_passed=gates,
            overall_status="pending",
        )
        self.release_candidates[rc.rc_id] = rc
        return rc

    def update_gate_status(self, rc_id: str, gate_name: str, passed: bool) -> ReleaseCandidate:
        """Update a specific gate. If all gates True, overall_status='approved'."""
        rc = self.release_candidates[rc_id]
        if gate_name in rc.gates_passed:
            rc.gates_passed[gate_name] = passed
            
        if all(rc.gates_passed.values()) and rc.gates_passed:
            rc.overall_status = "approved"
            
        return rc

    def approve_release(self, rc_id: str, approver: str) -> ReleaseCandidate:
        """Can only approve if all gates passed. Set approved_by."""
        rc = self.release_candidates[rc_id]
        if not rc.gates_passed or not all(rc.gates_passed.values()):
            raise ValueError(f"Cannot approve RC {rc_id}: not all gates passed")
            
        rc.overall_status = "released"
        rc.approved_by = approver
        return rc

    def reject_release(self, rc_id: str, reason: str) -> ReleaseCandidate:
        """Set overall_status='rejected'."""
        rc = self.release_candidates[rc_id]
        rc.overall_status = "rejected"
        return rc

    def register_support_policy(self, policy: SupportPolicy) -> None:
        """Register version support policy."""
        self.support_policies[policy.version] = policy

    def get_support_status(self, version: str) -> SupportStatus:
        """Look up current support status."""
        if version in self.support_policies:
            return self.support_policies[version].status
        return SupportStatus.END_OF_LIFE

    def get_eol_versions(self) -> List[str]:
        """Return versions at end-of-life."""
        return [p.version for p in self.support_policies.values() if p.status == SupportStatus.END_OF_LIFE]

    def check_security_backport_eligible(self, version: str) -> bool:
        """True if status is ACTIVE, MAINTENANCE, or SECURITY_ONLY."""
        if version not in self.support_policies:
            return False
        status = self.support_policies[version].status
        return status in (SupportStatus.ACTIVE, SupportStatus.MAINTENANCE, SupportStatus.SECURITY_ONLY)

    def generate_compatibility_matrix(self, versions: List[str]) -> Dict[Tuple[str, str], bool]:
        """For all version pairs, return compatibility based on registered checks."""
        matrix = {}
        for v1 in versions:
            for v2 in versions:
                if v1 == v2:
                    matrix[(v1, v2)] = True
                else:
                    matrix[(v1, v2)] = True
                    
        for check in self.compatibility_checks.values():
            if check.from_version in versions and check.to_version in versions:
                matrix[(check.from_version, check.to_version)] = check.backward_compatible
                
        return matrix

    def get_release_pipeline_status(self) -> Dict[str, Any]:
        """Summary: total_rcs, pending, approved, rejected, by_channel."""
        status = {
            "total_rcs": len(self.release_candidates),
            "pending": 0,
            "approved": 0,
            "rejected": 0,
            "by_channel": {}
        }
        for rc in self.release_candidates.values():
            s = rc.overall_status
            if s in status:
                status[s] += 1
            if s == "released":
                status["approved"] += 1
            ch = rc.channel
            status["by_channel"][ch] = status["by_channel"].get(ch, 0) + 1
        return status
